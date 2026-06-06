from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from backend.app.core.config import RESEARCH_CURRENT_ROOT
from backend.app.services.fine_theme_heat_db import connect_fine_heat_ro
from backend.app.services.selection_strategy_v2 import (
    SelectionV2Params,
    _apply_buy_costs,
    _apply_sell_costs,
    _compute_intent_profile,
    _is_limit_down_day,
    _is_limit_up_day,
    compute_v2_metrics,
    resolve_selection_v2_atomic_db_path,
)


STRATEGY_VERSION = "aggressive_10cm_v0_1"
DEFAULT_SELECTION_DB = os.getenv(
    "AGGRESSIVE_10CM_SELECTION_DB",
    os.path.join(RESEARCH_CURRENT_ROOT, "selection", "selection_research.db"),
)
DEFAULT_FINE_HEAT_DB = os.getenv(
    "AGGRESSIVE_10CM_FINE_HEAT_DB",
    os.path.join(RESEARCH_CURRENT_ROOT, "market_heat", "fine_theme_heat_daily_v2.db"),
)


@dataclass(frozen=True)
class Aggressive10cmParams:
    initial_budget: float = 1_000_000.0
    max_positions: int = 4
    max_new_positions_per_day: int = 3
    max_total_exposure_pct: float = 0.80
    per_position_pct: float = 0.24
    min_amount: float = 220_000_000.0
    min_score: float = 82.0
    candidate_scan_limit: int = 80
    max_open_gap_up_pct: float = 6.8
    max_open_gap_down_pct: float = -4.5
    first_15m_main_net_floor: float = 0.0
    first_15m_super_net_floor: float = 0.0
    first_15m_price_floor_pct: float = 0.0
    hard_stop_pct: float = -7.0
    first_take_profit_pct: float = 10.0
    first_take_profit_fraction: float = 0.50
    trailing_activate_pct: float = 15.0
    trailing_drawdown_pct: float = -8.0
    cum_super_peak_drawdown_pct: float = 25.0
    max_holding_days: int = 22
    buy_slippage_bp: float = 20.0
    sell_slippage_bp: float = 20.0
    round_trip_fee_bp: float = 22.0


def _connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    for schema_table in ("sqlite_temp_master", "sqlite_master"):
        row = conn.execute(
            f"SELECT name FROM {schema_table} WHERE type IN ('table', 'view') AND name=?",
            (table,),
        ).fetchone()
        if row:
            return True
    return False


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if float(denominator or 0.0) else 0.0


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _score_linear(value: Any, low: float, high: float) -> float:
    if high == low:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
        return 100.0 * _clip((float(value) - low) / (high - low))
    except Exception:
        return 0.0


def _is_mainboard_10cm_symbol(symbol: str) -> bool:
    s = str(symbol).lower()
    return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def _trade_dates_from_atomic(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    db_path: Optional[str] = None,
) -> List[str]:
    path = db_path or resolve_selection_v2_atomic_db_path()
    clauses: List[str] = []
    params: List[Any] = []
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect_ro(path) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT trade_date FROM atomic_trade_daily {where} ORDER BY trade_date ASC",
            params,
        ).fetchall()
    return [str(row[0]) for row in rows]


def _next_trade_date(trade_dates: Sequence[str], trade_date: str) -> Optional[str]:
    for day in trade_dates:
        if str(day) > str(trade_date):
            return str(day)
    return None


def _previous_trade_date(trade_dates: Sequence[str], trade_date: str) -> Optional[str]:
    previous = None
    for day in trade_dates:
        if str(day) >= str(trade_date):
            return previous
        previous = str(day)
    return previous


def load_daily_window(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    path = db_path or resolve_selection_v2_atomic_db_path()
    conditions = ["t.trade_date >= ?", "t.trade_date <= ?"]
    params: List[Any] = [start_date, end_date]
    if symbols:
        normalized = [str(symbol).strip().lower() for symbol in symbols if str(symbol).strip()]
        if normalized:
            placeholders = ",".join("?" for _ in normalized)
            conditions.append(f"lower(t.symbol) IN ({placeholders})")
            params.extend(normalized)
    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            lower(t.symbol) AS symbol,
            t.trade_date,
            t.open,
            t.high,
            t.low,
            t.close,
            t.total_amount,
            t.total_volume,
            t.trade_count,
            t.l1_main_net_amount,
            t.l2_main_net_amount,
            t.l1_super_net_amount,
            t.l2_super_net_amount,
            t.l2_buy_ratio,
            t.l2_sell_ratio,
            t.l1_buy_ratio,
            t.l1_sell_ratio,
            t.positive_l2_net_bar_count,
            t.negative_l2_net_bar_count,
            o.add_buy_amount,
            o.add_sell_amount,
            o.cancel_buy_amount,
            o.cancel_sell_amount,
            o.cvd_delta_amount,
            o.oib_delta_amount,
            o.positive_oib_bar_count,
            o.negative_oib_bar_count,
            o.positive_cvd_bar_count,
            o.negative_cvd_bar_count,
            o.buy_support_ratio,
            o.sell_pressure_ratio,
            o.order_event_count,
            l.board_type,
            l.risk_flag_type,
            l.touch_limit_up,
            l.touch_limit_down,
            l.is_limit_up_close,
            l.is_limit_down_close,
            l.broken_limit_up,
            l.broken_limit_down,
            l.limit_state_label
        FROM atomic_trade_daily AS t
        LEFT JOIN atomic_order_daily AS o
          ON o.symbol = t.symbol
         AND o.trade_date = t.trade_date
        LEFT JOIN atomic_limit_state_daily AS l
          ON l.symbol = t.symbol
         AND l.trade_date = t.trade_date
        WHERE {where}
          AND (
            lower(t.symbol) LIKE 'sh600%'
            OR lower(t.symbol) LIKE 'sh601%'
            OR lower(t.symbol) LIKE 'sh603%'
            OR lower(t.symbol) LIKE 'sh605%'
            OR lower(t.symbol) LIKE 'sz000%'
            OR lower(t.symbol) LIKE 'sz001%'
            OR lower(t.symbol) LIKE 'sz002%'
            OR lower(t.symbol) LIKE 'sz003%'
          )
        ORDER BY lower(t.symbol) ASC, t.trade_date ASC
    """
    with _connect_ro(path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        return df

    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "total_amount",
        "total_volume",
        "trade_count",
        "l1_main_net_amount",
        "l2_main_net_amount",
        "l1_super_net_amount",
        "l2_super_net_amount",
        "l2_buy_ratio",
        "l2_sell_ratio",
        "l1_buy_ratio",
        "l1_sell_ratio",
        "positive_l2_net_bar_count",
        "negative_l2_net_bar_count",
        "add_buy_amount",
        "add_sell_amount",
        "cancel_buy_amount",
        "cancel_sell_amount",
        "cvd_delta_amount",
        "oib_delta_amount",
        "positive_oib_bar_count",
        "negative_oib_bar_count",
        "positive_cvd_bar_count",
        "negative_cvd_bar_count",
        "buy_support_ratio",
        "sell_pressure_ratio",
        "order_event_count",
        "touch_limit_up",
        "touch_limit_down",
        "is_limit_up_close",
        "is_limit_down_close",
        "broken_limit_up",
        "broken_limit_down",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["board_type"] = df["board_type"].fillna("").astype(str)
    df["risk_flag_type"] = df["risk_flag_type"].fillna("normal").astype(str)
    df["limit_state_label"] = df["limit_state_label"].fillna("").astype(str)
    return df


def _load_selection_signals(start_date: str, end_date: str, selection_db_path: Optional[str]) -> pd.DataFrame:
    path = selection_db_path or DEFAULT_SELECTION_DB
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    try:
        with _connect_ro(path) as conn:
            if not _table_exists(conn, "selection_signal_daily"):
                return pd.DataFrame()
            df = pd.read_sql_query(
                """
                SELECT
                    lower(symbol) AS symbol,
                    trade_date,
                    stealth_score AS v1_stealth_score,
                    breakout_score AS v1_breakout_score,
                    distribution_score AS v1_distribution_score,
                    inflow_quality_score AS v1_inflow_quality_score,
                    l2_distribution_score AS v1_l2_distribution_score
                FROM selection_signal_daily
                WHERE trade_date >= ? AND trade_date <= ?
                """,
                conn,
                params=[start_date, end_date],
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for col in df.columns:
        if col not in {"symbol", "trade_date"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _load_theme_members(start_date: str, end_date: str, fine_heat_db_path: Optional[str]) -> pd.DataFrame:
    path = fine_heat_db_path or DEFAULT_FINE_HEAT_DB
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    try:
        with connect_fine_heat_ro(path) as conn:
            if not (_table_exists(conn, "fine_theme_member_daily") and _table_exists(conn, "fine_theme_heat_daily")):
                return pd.DataFrame()
            df = pd.read_sql_query(
                """
                SELECT
                    lower(m.symbol) AS symbol,
                    m.trade_date,
                    m.name AS theme_stock_name,
                    m.sector_name AS hot_theme_name,
                    h.hot_rank AS hot_theme_rank,
                    h.hot_score AS hot_theme_score,
                    h.persistence_score AS hot_theme_persistence_score,
                    h.risk_tags_json AS hot_theme_risk_tags
                FROM fine_theme_member_daily AS m
                JOIN fine_theme_heat_daily AS h
                  ON h.trade_date = m.trade_date
                 AND h.theme_id = m.theme_id
                WHERE m.trade_date >= ? AND m.trade_date <= ?
                  AND h.hot_rank <= 15
                ORDER BY m.trade_date ASC, lower(m.symbol) ASC, h.hot_rank ASC
                """,
                conn,
                params=[start_date, end_date],
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    numeric_cols = ["hot_theme_rank", "hot_theme_score", "hot_theme_persistence_score"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.drop_duplicates(["symbol", "trade_date"], keep="first")


def prepare_metrics(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    selection_db_path: Optional[str] = None,
    fine_heat_db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    raw = load_daily_window(start_date, end_date, db_path=db_path, symbols=symbols)
    if raw.empty:
        return raw
    metrics = compute_v2_metrics(raw)
    frames: List[pd.DataFrame] = []
    for _, group in metrics.groupby("symbol", sort=False):
        g = group.sort_values("trade_date").copy()
        amount_5 = g["total_amount"].rolling(5, min_periods=3).sum()
        amount_10 = g["total_amount"].rolling(10, min_periods=5).sum()
        amount_20 = g["total_amount"].rolling(20, min_periods=8).sum()
        g["close_ma5"] = g["close"].rolling(5, min_periods=3).mean()
        g["close_ma10"] = g["close"].rolling(10, min_periods=5).mean()
        g["close_ma20"] = g["close"].rolling(20, min_periods=8).mean()
        g["main_net_10d_ratio"] = (g["l2_main_net_amount"].rolling(10, min_periods=5).sum() / amount_10.replace(0, pd.NA)).fillna(0.0)
        g["super_net_10d_ratio"] = (g["l2_super_net_amount"].rolling(10, min_periods=5).sum() / amount_10.replace(0, pd.NA)).fillna(0.0)
        g["main_net_20d_ratio"] = (g["l2_main_net_amount"].rolling(20, min_periods=8).sum() / amount_20.replace(0, pd.NA)).fillna(0.0)
        g["super_net_20d_ratio"] = (g["l2_super_net_amount"].rolling(20, min_periods=8).sum() / amount_20.replace(0, pd.NA)).fillna(0.0)
        g["main_net_5d_ratio"] = (g["l2_main_net_amount"].rolling(5, min_periods=3).sum() / amount_5.replace(0, pd.NA)).fillna(0.0)
        g["super_net_5d_ratio"] = (g["l2_super_net_amount"].rolling(5, min_periods=3).sum() / amount_5.replace(0, pd.NA)).fillna(0.0)
        g["positive_main_day_ratio_10d"] = g["l2_main_net_amount"].gt(0).rolling(10, min_periods=5).mean().fillna(0.0)
        g["positive_super_day_ratio_10d"] = g["l2_super_net_amount"].gt(0).rolling(10, min_periods=5).mean().fillna(0.0)
        g["price_vs_ma10_pct"] = ((g["close"] / g["close_ma10"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        g["price_vs_ma20_pct"] = ((g["close"] / g["close_ma20"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        g["prev_high_20d"] = g["high"].shift(1).rolling(20, min_periods=8).max()
        g["close_vs_prev_high20_pct"] = ((g["close"] / g["prev_high_20d"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        frames.append(g)
    metrics = pd.concat(frames, ignore_index=True)

    selection = _load_selection_signals(start_date, end_date, selection_db_path)
    if not selection.empty:
        metrics = metrics.merge(selection, on=["symbol", "trade_date"], how="left")
    theme = _load_theme_members(start_date, end_date, fine_heat_db_path)
    if not theme.empty:
        metrics = metrics.merge(theme, on=["symbol", "trade_date"], how="left")

    defaults: Dict[str, Any] = {
        "v1_stealth_score": 0.0,
        "v1_breakout_score": 0.0,
        "v1_distribution_score": 0.0,
        "v1_inflow_quality_score": 0.0,
        "v1_l2_distribution_score": 0.0,
        "hot_theme_rank": 999.0,
        "hot_theme_score": 0.0,
        "hot_theme_persistence_score": 0.0,
        "hot_theme_name": "",
        "theme_stock_name": "",
        "hot_theme_risk_tags": "",
    }
    for col, value in defaults.items():
        if col not in metrics.columns:
            metrics[col] = value
        else:
            metrics[col] = metrics[col].fillna(value)
    return metrics


def _market_regime(day_df: pd.DataFrame) -> Dict[str, Any]:
    if day_df.empty:
        return {
            "score": 50.0,
            "label": "unknown",
            "target_exposure_pct": 0.50,
            "advancing_ratio": 0.0,
            "median_return_pct": 0.0,
            "l2_main_net_ratio": 0.0,
            "limit_up_count": 0,
        }
    returns = pd.to_numeric(day_df["return_1d_pct"], errors="coerce").fillna(0.0)
    amount = pd.to_numeric(day_df["total_amount"], errors="coerce").fillna(0.0)
    main_net = pd.to_numeric(day_df["l2_main_net_amount"], errors="coerce").fillna(0.0)
    advancing_ratio = float((returns > 0).mean() * 100.0)
    median_return = float(returns.median())
    l2_main_ratio = float(main_net.sum() / max(amount.sum(), 1.0))
    limit_up_count = int((returns >= 9.5).sum())
    score = (
        0.34 * _score_linear(advancing_ratio, 38.0, 62.0)
        + 0.26 * _score_linear(median_return, -1.0, 1.2)
        + 0.28 * _score_linear(l2_main_ratio, -0.025, 0.025)
        + 0.12 * _score_linear(limit_up_count, 20.0, 80.0)
    )
    if score >= 68.0:
        label = "strong"
        target_exposure = 0.80
    elif score >= 52.0:
        label = "neutral"
        target_exposure = 0.60
    elif score >= 42.0:
        label = "defensive"
        target_exposure = 0.40
    else:
        label = "weak"
        target_exposure = 0.25
    return {
        "score": round(score, 2),
        "label": label,
        "target_exposure_pct": target_exposure,
        "advancing_ratio": round(advancing_ratio, 2),
        "median_return_pct": round(median_return, 2),
        "l2_main_net_ratio": round(l2_main_ratio, 5),
        "limit_up_count": limit_up_count,
    }


def _candidate_type_and_reasons(row: pd.Series, intent: Dict[str, Any], params: Aggressive10cmParams) -> Tuple[List[str], List[str], List[str]]:
    types: List[str] = []
    reasons: List[str] = []
    warnings: List[str] = []
    total_amount = float(row.get("total_amount") or 0.0)
    return_1d = float(row.get("return_1d_pct") or 0.0)
    return_20d = float(row.get("return_20d_pct") or 0.0)
    amount_anomaly = float(row.get("amount_anomaly_20d") or 0.0)
    active = float(row.get("active_buy_strength") or 0.0)
    l2_main = float(row.get("l2_main_net_ratio") or 0.0)
    l2_super = float(row.get("l2_super_net_ratio") or 0.0)
    attack = float(intent.get("attack_score") or 0.0)
    repair = float(intent.get("repair_score") or 0.0)
    accumulation = float(intent.get("accumulation_score") or 0.0)
    distribution = float(intent.get("distribution_score") or 0.0)
    near_high = float(row.get("max_drawdown_from_20d_high_pct") or 0.0) >= -12.0

    if total_amount < params.min_amount:
        warnings.append("成交额低于进攻池门槛")
        return types, reasons, warnings
    if distribution >= 82.0 or str(intent.get("intent_label")) in {"panic_distribution", "pull_up_distribution"}:
        warnings.append("出货/派发风险过高")
        return types, reasons, warnings

    if (
        attack >= 58.0
        and amount_anomaly >= 1.12
        and active > 0
        and return_1d >= 1.5
        and l2_main >= -0.008
    ):
        types.append("launch_attack")
        reasons.append("放量攻击且主动买入转强")

    if (
        repair >= 56.0
        and float(row.get("prior_3d_min_return_1d_pct") or 0.0) <= -3.0
        and float(row.get("support_pressure_spread") or 0.0) >= -0.05
        and l2_main >= -0.012
    ):
        types.append("shakeout_repair")
        reasons.append("急跌/分歧后出现资金承接修复")

    if (
        8.0 <= return_20d <= 78.0
        and near_high
        and amount_anomaly >= 1.08
        and active > 0.0
        and (return_1d >= 1.8 or attack >= 48.0)
        and (float(row.get("super_net_5d_ratio") or 0.0) > -0.006 or l2_super > -0.006)
    ):
        types.append("second_wave")
        reasons.append("强趋势高位附近未见明显超大单撤退")

    if (
        accumulation >= 62.0
        and attack >= 50.0
        and return_20d <= 38.0
        and amount_anomaly >= 1.08
        and float(row.get("main_net_10d_ratio") or 0.0) > 0.006
        and (return_1d >= 1.8 or float(row.get("breakout_vs_prev20_high_pct") or 0.0) >= 0.0)
    ):
        types.append("accumulation_to_launch")
        reasons.append("中短期资金吸筹后开始异动")

    if float(row.get("v1_breakout_score") or 0.0) >= 65.0 and distribution < 70.0:
        types.append("selection_v1_resonance")
        reasons.append("现有选股信号与进攻信号共振")

    if float(row.get("hot_theme_rank") or 999.0) <= 10.0:
        reasons.append(f"处于热门细分主题：{str(row.get('hot_theme_name') or '')}")

    if return_20d > 70.0:
        warnings.append("20日涨幅偏高，开盘不能追过热缺口")
    if distribution >= 68.0:
        warnings.append("出货分抬升，需缩小仓位或等待承接")
    if return_1d >= 9.3:
        warnings.append("信号日接近涨停，次日高开需放弃追价")
    return types, reasons, warnings


def _score_candidate(row: pd.Series, intent: Dict[str, Any], market: Dict[str, Any]) -> float:
    attack = float(intent.get("attack_score") or 0.0)
    repair = float(intent.get("repair_score") or 0.0)
    accumulation = float(intent.get("accumulation_score") or 0.0)
    distribution = float(intent.get("distribution_score") or 0.0)
    funding_score = (
        0.38 * _score_linear(row.get("l2_main_net_ratio"), -0.008, 0.05)
        + 0.26 * _score_linear(row.get("l2_super_net_ratio"), -0.006, 0.025)
        + 0.18 * _score_linear(row.get("main_net_10d_ratio"), -0.012, 0.045)
        + 0.18 * _score_linear(row.get("super_net_10d_ratio"), -0.008, 0.025)
    )
    activity_score = (
        0.55 * _score_linear(row.get("amount_anomaly_20d"), 0.85, 2.4)
        + 0.45 * _score_linear(row.get("active_buy_strength"), -1.0, 9.0)
    )
    structure_score = (
        0.35 * _score_linear(row.get("breakout_vs_prev20_high_pct"), -2.0, 5.0)
        + 0.25 * _score_linear(row.get("close_vs_prev_high20_pct"), -7.0, 2.0)
        + 0.20 * _score_linear(row.get("price_vs_ma10_pct"), -4.0, 8.0)
        + 0.20 * _score_linear(row.get("max_drawdown_from_20d_high_pct"), -18.0, -2.0)
    )
    selection_score = (
        0.45 * _score_linear(row.get("v1_breakout_score"), 45.0, 85.0)
        + 0.35 * _score_linear(row.get("v1_stealth_score"), 45.0, 85.0)
        + 0.20 * _score_linear(row.get("v1_inflow_quality_score"), 35.0, 85.0)
    )
    theme_score = 0.0
    if float(row.get("hot_theme_rank") or 999.0) <= 15.0:
        theme_score = 0.65 * _score_linear(16.0 - float(row.get("hot_theme_rank") or 999.0), 1.0, 15.0) + 0.35 * _score_linear(row.get("hot_theme_score"), 65.0, 95.0)
    overheat_penalty = _score_linear(row.get("return_20d_pct"), 45.0, 120.0)
    distribution_penalty = _score_linear(distribution, 58.0, 90.0)
    score = (
        0.17 * attack
        + 0.13 * repair
        + 0.10 * accumulation
        + 0.17 * funding_score
        + 0.13 * activity_score
        + 0.13 * structure_score
        + 0.07 * selection_score
        + 0.05 * theme_score
        + 0.05 * float(market.get("score") or 50.0)
        - 0.10 * overheat_penalty
        - 0.14 * distribution_penalty
    )
    return round(max(0.0, min(100.0, score)), 2)


def screen_candidates(
    metrics: pd.DataFrame,
    signal_date: str,
    *,
    params: Optional[Aggressive10cmParams] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    active_params = params or Aggressive10cmParams()
    day_df = metrics[metrics["trade_date"] == signal_date].copy()
    if day_df.empty:
        return {
            "signal_date": signal_date,
            "strategy_version": STRATEGY_VERSION,
            "market_regime": _market_regime(day_df),
            "items": [],
        }
    day_df = day_df[
        day_df["symbol"].map(_is_mainboard_10cm_symbol)
        & day_df["risk_flag_type"].fillna("normal").eq("normal")
    ].copy()
    market = _market_regime(day_df)
    items: List[Dict[str, Any]] = []
    for _, row in day_df.iterrows():
        intent = _compute_intent_profile(row, SelectionV2Params())
        candidate_types, reasons, warnings = _candidate_type_and_reasons(row, intent, active_params)
        if not candidate_types:
            continue
        score = _score_candidate(row, intent, market)
        if score < active_params.min_score:
            continue
        name = str(row.get("theme_stock_name") or row.get("symbol") or "")
        items.append(
            {
                "symbol": str(row["symbol"]),
                "name": name,
                "signal_date": signal_date,
                "score": score,
                "candidate_types": candidate_types,
                "reasons": reasons[:4],
                "warnings": warnings[:4],
                "close": round(float(row.get("close") or 0.0), 4),
                "metrics": {
                    "return_1d_pct": round(float(row.get("return_1d_pct") or 0.0), 2),
                    "return_5d_pct": round(float(row.get("return_5d_pct") or 0.0), 2),
                    "return_20d_pct": round(float(row.get("return_20d_pct") or 0.0), 2),
                    "amount_yi": round(float(row.get("total_amount") or 0.0) / 100_000_000.0, 2),
                    "amount_anomaly_20d": round(float(row.get("amount_anomaly_20d") or 0.0), 3),
                    "l2_main_net_ratio": round(float(row.get("l2_main_net_ratio") or 0.0), 5),
                    "l2_super_net_ratio": round(float(row.get("l2_super_net_ratio") or 0.0), 5),
                    "main_net_10d_ratio": round(float(row.get("main_net_10d_ratio") or 0.0), 5),
                    "super_net_10d_ratio": round(float(row.get("super_net_10d_ratio") or 0.0), 5),
                    "active_buy_strength": round(float(row.get("active_buy_strength") or 0.0), 4),
                    "support_pressure_spread": round(float(row.get("support_pressure_spread") or 0.0), 5),
                    "breakout_vs_prev20_high_pct": round(float(row.get("breakout_vs_prev20_high_pct") or 0.0), 2),
                },
                "intent_profile": {
                    "intent_label": str(intent.get("intent_label") or ""),
                    "accumulation_score": round(float(intent.get("accumulation_score") or 0.0), 2),
                    "attack_score": round(float(intent.get("attack_score") or 0.0), 2),
                    "repair_score": round(float(intent.get("repair_score") or 0.0), 2),
                    "distribution_score": round(float(intent.get("distribution_score") or 0.0), 2),
                },
                "theme": {
                    "name": str(row.get("hot_theme_name") or ""),
                    "rank": None if float(row.get("hot_theme_rank") or 999.0) >= 999.0 else int(float(row.get("hot_theme_rank") or 0.0)),
                    "score": round(float(row.get("hot_theme_score") or 0.0), 2),
                },
            }
        )
    items = sorted(items, key=lambda item: (-float(item["score"]), str(item["symbol"])))[: int(limit)]
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return {
        "signal_date": signal_date,
        "strategy_version": STRATEGY_VERSION,
        "market_regime": market,
        "params": asdict(active_params),
        "items": items,
    }


def _selection_start(signal_start: str, lookback_days: int = 140) -> str:
    return (pd.Timestamp(signal_start) - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")


def build_trade_plan(
    signal_date: str,
    *,
    budget: float = 1_000_000.0,
    params: Optional[Aggressive10cmParams] = None,
    top_n: int = 12,
    db_path: Optional[str] = None,
    selection_db_path: Optional[str] = None,
    fine_heat_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = params or Aggressive10cmParams(initial_budget=budget)
    trade_dates = _trade_dates_from_atomic(end_date=signal_date, db_path=db_path)
    latest_data_date = trade_dates[-1] if trade_dates else signal_date
    if signal_date > latest_data_date:
        signal_date = latest_data_date
    start = _selection_start(signal_date)
    metrics = prepare_metrics(
        start,
        signal_date,
        db_path=db_path,
        selection_db_path=selection_db_path,
        fine_heat_db_path=fine_heat_db_path,
    )
    candidates = screen_candidates(metrics, signal_date, params=active_params, limit=max(top_n, active_params.candidate_scan_limit))
    future_dates = _trade_dates_from_atomic(start_date=signal_date, db_path=db_path)
    entry_date = _next_trade_date(future_dates, signal_date)
    if entry_date is None:
        entry_date = pd.bdate_range(pd.Timestamp(signal_date) + pd.Timedelta(days=1), periods=1).strftime("%Y-%m-%d")[0]
    market = candidates["market_regime"]
    target_exposure_pct = min(float(active_params.max_total_exposure_pct), float(market.get("target_exposure_pct") or 0.5))
    max_capital = float(budget) * target_exposure_pct
    selected_count = max(1, min(int(active_params.max_positions), len(candidates["items"])))
    per_position = min(float(budget) * float(active_params.per_position_pct), max_capital / selected_count if selected_count else 0.0)
    plan_items: List[Dict[str, Any]] = []
    for item in candidates["items"][: selected_count]:
        signal_close = float(item["close"])
        max_buy_price = signal_close * (1.0 + active_params.max_open_gap_up_pct / 100.0)
        min_buy_price = signal_close * (1.0 + active_params.max_open_gap_down_pct / 100.0)
        plan_items.append(
            {
                **item,
                "planned_entry_date": entry_date,
                "planned_capital": round(per_position, 2),
                "planned_capital_pct": round(per_position / float(budget) * 100.0, 2) if budget else 0.0,
                "buy_trigger": {
                    "window": "09:35-09:45",
                    "price_range": [round(min_buy_price, 3), round(max_buy_price, 3)],
                "rules": [
                    "不买一字/秒板涨停，开盘缺口超过上限放弃",
                    f"前15分钟价格相对开盘涨跌幅不能低于 {active_params.first_15m_price_floor_pct:.1f}%",
                    "前15分钟L2主力/超大单不能同时低于设定净流入阈值",
                    "若触发但盘口承接弱，保留现金，不强行满仓",
                ],
                },
                "risk_control": {
                    "hard_stop_pct": active_params.hard_stop_pct,
                    "first_take_profit_pct": active_params.first_take_profit_pct,
                    "first_take_profit_fraction": active_params.first_take_profit_fraction,
                    "trailing_activate_pct": active_params.trailing_activate_pct,
                    "trailing_drawdown_pct": active_params.trailing_drawdown_pct,
                    "max_holding_days": active_params.max_holding_days,
                },
            }
        )
    return {
        "strategy_version": STRATEGY_VERSION,
        "signal_date": signal_date,
        "planned_entry_date": entry_date,
        "budget": float(budget),
        "target_exposure_pct": round(target_exposure_pct * 100.0, 2),
        "target_exposure_capital": round(max_capital, 2),
        "market_regime": market,
        "items": plan_items,
        "candidate_count": len(candidates["items"]),
        "data_note": "所有候选只使用 signal_date 收盘及以前可见数据；买入规则用于 planned_entry_date 开盘后确认。",
    }


def _query_first_15m(
    symbol: str,
    trade_date: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    path = db_path or resolve_selection_v2_atomic_db_path()
    with _connect_ro(path) as conn:
        rows = conn.execute(
            """
            SELECT bucket_start, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_5m
            WHERE lower(symbol)=lower(?) AND trade_date=?
            ORDER BY bucket_start ASC
            LIMIT 3
            """,
            (symbol, trade_date),
        ).fetchall()
    if not rows:
        return None
    first_open = float(rows[0]["open"])
    last_close = float(rows[-1]["close"])
    high = max(float(row["high"]) for row in rows)
    low = min(float(row["low"]) for row in rows)
    amount = sum(float(row["total_amount"] or 0.0) for row in rows)
    main_net = sum(float(row["l2_main_net_amount"] or 0.0) for row in rows)
    super_net = sum(float(row["l2_super_net_amount"] or 0.0) for row in rows)
    return {
        "first_open": first_open,
        "confirm_price": last_close,
        "first_15m_high": high,
        "first_15m_low": low,
        "first_15m_amount": amount,
        "first_15m_main_net_ratio": _safe_ratio(main_net, amount),
        "first_15m_super_net_ratio": _safe_ratio(super_net, amount),
        "first_15m_price_return_pct": ((last_close / first_open) - 1.0) * 100.0 if first_open > 0 else 0.0,
    }


def _confirm_entry(
    candidate: Dict[str, Any],
    entry_row: pd.Series,
    *,
    params: Aggressive10cmParams,
    db_path: Optional[str] = None,
) -> Tuple[bool, float, Dict[str, Any]]:
    signal_close = float(candidate.get("close") or 0.0)
    open_price = float(entry_row.get("open") or 0.0)
    if signal_close <= 0 or open_price <= 0:
        return False, 0.0, {"reason": "invalid_price"}
    if _is_limit_up_day(entry_row, SelectionV2Params()):
        return False, 0.0, {"reason": "entry_blocked_limit_up"}
    gap_pct = ((open_price / signal_close) - 1.0) * 100.0
    if gap_pct > params.max_open_gap_up_pct:
        return False, 0.0, {"reason": "open_gap_too_high", "open_gap_pct": round(gap_pct, 2)}
    if gap_pct < params.max_open_gap_down_pct:
        return False, 0.0, {"reason": "open_gap_too_weak", "open_gap_pct": round(gap_pct, 2)}

    first_15m = _query_first_15m(str(candidate["symbol"]), str(entry_row["trade_date"]), db_path=db_path)
    if not first_15m:
        return True, open_price, {"reason": "fallback_daily_open", "open_gap_pct": round(gap_pct, 2)}
    price_ret = float(first_15m["first_15m_price_return_pct"])
    main_ratio = float(first_15m["first_15m_main_net_ratio"])
    super_ratio = float(first_15m["first_15m_super_net_ratio"])
    if price_ret < params.first_15m_price_floor_pct:
        return False, float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_price_broke"}
    if main_ratio < params.first_15m_main_net_floor and super_ratio < params.first_15m_super_net_floor:
        return False, float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_l2_outflow"}
    return True, float(first_15m["confirm_price"]), {**first_15m, "reason": "confirmed_09_45", "open_gap_pct": round(gap_pct, 2)}


def _row_by_symbol_date(metrics: pd.DataFrame) -> Dict[Tuple[str, str], pd.Series]:
    return {(str(row["symbol"]), str(row["trade_date"])): row for _, row in metrics.iterrows()}


def _portfolio_summary(
    trades: Sequence[Dict[str, Any]],
    equity_curve: Sequence[Dict[str, Any]],
    initial_budget: float,
) -> Dict[str, Any]:
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else float(initial_budget)
    returns = pd.Series([float(trade.get("net_return_pct") or 0.0) for trade in trades])
    win_rate = round(float((returns > 0).mean() * 100.0), 2) if not returns.empty else 0.0
    equity = pd.Series([float(item["equity"]) for item in equity_curve]) if equity_curve else pd.Series(dtype=float)
    if equity.empty:
        max_drawdown = 0.0
    else:
        max_drawdown = round(float(((equity / equity.cummax()) - 1.0).min() * 100.0), 2)
    return {
        "initial_budget": round(float(initial_budget), 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / float(initial_budget) - 1.0) * 100.0, 2) if initial_budget else 0.0,
        "trade_count": int(len(trades)),
        "win_rate_pct": win_rate,
        "avg_net_return_pct": round(float(returns.mean()), 2) if not returns.empty else 0.0,
        "median_net_return_pct": round(float(returns.median()), 2) if not returns.empty else 0.0,
        "max_net_return_pct": round(float(returns.max()), 2) if not returns.empty else 0.0,
        "min_net_return_pct": round(float(returns.min()), 2) if not returns.empty else 0.0,
        "max_drawdown_pct": max_drawdown,
    }


def backtest_range(
    start_date: str,
    end_date: str,
    *,
    replay_end_date: Optional[str] = None,
    budget: float = 1_000_000.0,
    params: Optional[Aggressive10cmParams] = None,
    top_n: int = 12,
    db_path: Optional[str] = None,
    selection_db_path: Optional[str] = None,
    fine_heat_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = params or Aggressive10cmParams(initial_budget=budget)
    trade_dates_all = _trade_dates_from_atomic(db_path=db_path)
    if not trade_dates_all:
        return {"summary": _portfolio_summary([], [], budget), "trades": [], "daily_results": [], "equity_curve": []}
    resolved_replay_end = replay_end_date or min(
        trade_dates_all[-1],
        (pd.Timestamp(end_date) + pd.Timedelta(days=70)).strftime("%Y-%m-%d"),
    )
    metrics_start = _selection_start(start_date)
    metrics = prepare_metrics(
        metrics_start,
        resolved_replay_end,
        db_path=db_path,
        selection_db_path=selection_db_path,
        fine_heat_db_path=fine_heat_db_path,
    )
    if metrics.empty:
        return {"summary": _portfolio_summary([], [], budget), "trades": [], "daily_results": [], "equity_curve": []}
    row_map = _row_by_symbol_date(metrics)
    simulation_dates = [d for d in sorted(metrics["trade_date"].unique()) if start_date <= d <= resolved_replay_end]
    signal_dates = [d for d in simulation_dates if start_date <= d <= end_date]

    pending_entries: Dict[str, List[Dict[str, Any]]] = {}
    daily_screen: List[Dict[str, Any]] = []
    for signal_date in signal_dates:
        candidates = screen_candidates(metrics, signal_date, params=active_params, limit=top_n)
        entry_date = _next_trade_date(simulation_dates, signal_date)
        daily_screen.append(
            {
                "signal_date": signal_date,
                "candidate_count": len(candidates["items"]),
                "market_regime": candidates["market_regime"],
                "entry_date": entry_date,
            }
        )
        if not entry_date:
            continue
        for candidate in candidates["items"][:top_n]:
            pending_entries.setdefault(entry_date, []).append({**candidate, "planned_entry_date": entry_date})

    cost_params = SelectionV2Params(
        buy_slippage_bp=active_params.buy_slippage_bp,
        sell_slippage_bp=active_params.sell_slippage_bp,
        round_trip_fee_bp=active_params.round_trip_fee_bp,
    )
    cash = float(budget)
    positions: Dict[str, Dict[str, Any]] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    daily_results: List[Dict[str, Any]] = []

    def close_position(pos: Dict[str, Any], trade_date: str, gross_exit: float, reason: str) -> None:
        nonlocal cash
        exit_price = _apply_sell_costs(float(gross_exit), cost_params)
        proceeds = float(pos["shares"]) * exit_price
        cash += proceeds
        realized_cash = float(pos.get("realized_cash") or 0.0) + proceeds
        invested_cash = float(pos["invested_cash"])
        net_return_pct = ((realized_cash / invested_cash) - 1.0) * 100.0 if invested_cash else 0.0
        trades.append(
            {
                "symbol": pos["symbol"],
                "name": pos.get("name") or pos["symbol"],
                "signal_date": pos["signal_date"],
                "entry_date": pos["entry_date"],
                "exit_date": trade_date,
                "gross_entry_price": round(float(pos["gross_entry_price"]), 4),
                "gross_exit_price": round(float(gross_exit), 4),
                "invested_cash": round(invested_cash, 2),
                "realized_cash": round(realized_cash, 2),
                "net_return_pct": round(net_return_pct, 2),
                "max_runup_pct": round(float(pos.get("max_runup_pct") or 0.0), 2),
                "max_drawdown_pct": round(float(pos.get("max_drawdown_pct") or 0.0), 2),
                "holding_days": int(pos.get("holding_days") or 0),
                "exit_reason": reason,
                "score": pos.get("score"),
                "candidate_types": pos.get("candidate_types", []),
            }
        )
        positions.pop(pos["symbol"], None)

    for trade_date in simulation_dates:
        opened = 0
        skipped = 0
        exited = 0

        for symbol, pos in list(positions.items()):
            row = row_map.get((symbol, trade_date))
            if row is None:
                continue
            if pos.get("pending_exit_reason"):
                if _is_limit_down_day(row, cost_params):
                    continue
                close_position(pos, trade_date, float(row["open"]), str(pos["pending_exit_reason"]))
                exited += 1
                continue

            pos["holding_days"] = int(pos.get("holding_days") or 0) + 1
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            entry = float(pos["gross_entry_price"])
            pos["peak_price"] = max(float(pos.get("peak_price") or entry), high)
            pos["max_runup_pct"] = max(float(pos.get("max_runup_pct") or 0.0), ((high / entry) - 1.0) * 100.0)
            pos["max_drawdown_pct"] = min(float(pos.get("max_drawdown_pct") or 0.0), ((low / entry) - 1.0) * 100.0)
            daily_super = float(row.get("l2_super_net_amount") or 0.0)
            pos["cum_super"] = float(pos.get("cum_super") or 0.0) + daily_super
            pos["cum_amount"] = float(pos.get("cum_amount") or 0.0) + float(row.get("total_amount") or 0.0)
            pos["cum_super_peak"] = max(float(pos.get("cum_super_peak") or 0.0), float(pos["cum_super"]))
            close_return = ((close / entry) - 1.0) * 100.0

            if not pos.get("partial_taken") and high >= entry * (1.0 + active_params.first_take_profit_pct / 100.0):
                sell_shares = float(pos["shares"]) * float(active_params.first_take_profit_fraction)
                take_price = entry * (1.0 + active_params.first_take_profit_pct / 100.0)
                proceeds = sell_shares * _apply_sell_costs(take_price, cost_params)
                cash += proceeds
                pos["shares"] = float(pos["shares"]) - sell_shares
                pos["realized_cash"] = float(pos.get("realized_cash") or 0.0) + proceeds
                pos["partial_taken"] = True

            if low <= entry * (1.0 + active_params.hard_stop_pct / 100.0):
                if _is_limit_down_day(row, cost_params):
                    pos["pending_exit_reason"] = "stop_blocked_limit_down"
                else:
                    stop_price = min(float(row["open"]), entry * (1.0 + active_params.hard_stop_pct / 100.0)) if float(row["open"]) < entry else entry * (1.0 + active_params.hard_stop_pct / 100.0)
                    close_position(pos, trade_date, stop_price, "hard_stop")
                    exited += 1
                continue

            peak_return = ((float(pos.get("peak_price") or entry) / entry) - 1.0) * 100.0
            peak_drawdown = ((close / float(pos.get("peak_price") or entry)) - 1.0) * 100.0
            cum_super_peak = float(pos.get("cum_super_peak") or 0.0)
            cum_super = float(pos.get("cum_super") or 0.0)
            super_peak_dd = ((cum_super_peak - cum_super) / cum_super_peak * 100.0) if cum_super_peak > 0 else 0.0
            intent = _compute_intent_profile(row, SelectionV2Params())
            distribution = float(intent.get("distribution_score") or 0.0)
            if peak_return >= active_params.trailing_activate_pct and peak_drawdown <= active_params.trailing_drawdown_pct:
                pos["pending_exit_reason"] = "trailing_drawdown"
            elif cum_super_peak > 0 and super_peak_dd >= active_params.cum_super_peak_drawdown_pct and close_return >= 0:
                pos["pending_exit_reason"] = "cum_super_peak_drawdown"
            elif distribution >= 82.0 and float(row.get("l2_main_net_ratio") or 0.0) < 0:
                pos["pending_exit_reason"] = "distribution_exit"
            elif int(pos.get("holding_days") or 0) >= active_params.max_holding_days:
                pos["pending_exit_reason"] = "max_holding_days"

        entries = sorted(pending_entries.get(trade_date, []), key=lambda item: (-float(item["score"]), str(item["symbol"])))
        for candidate in entries:
            if opened >= active_params.max_new_positions_per_day:
                skipped += 1
                continue
            if candidate["symbol"] in positions:
                skipped += 1
                continue
            if len(positions) >= active_params.max_positions:
                skipped += 1
                continue
            row = row_map.get((str(candidate["symbol"]), trade_date))
            if row is None:
                skipped += 1
                continue
            equity_now = cash + sum(
                float(pos["shares"]) * float(row_map.get((str(pos["symbol"]), trade_date), {}).get("close", pos["gross_entry_price"]))
                for pos in positions.values()
            )
            max_exposure = float(budget) * float(active_params.max_total_exposure_pct)
            current_exposure = sum(float(pos["shares"]) * float(pos["gross_entry_price"]) for pos in positions.values())
            available_exposure = max(0.0, max_exposure - current_exposure)
            target_cash = min(float(budget) * float(active_params.per_position_pct), available_exposure, cash)
            if target_cash <= 5_000:
                skipped += 1
                continue
            ok, gross_entry, entry_meta = _confirm_entry(candidate, row, params=active_params, db_path=db_path)
            if not ok or gross_entry <= 0:
                skipped += 1
                continue
            effective_entry = _apply_buy_costs(gross_entry, cost_params)
            shares = target_cash / effective_entry
            cash -= target_cash
            positions[str(candidate["symbol"])] = {
                "symbol": str(candidate["symbol"]),
                "name": candidate.get("name") or candidate["symbol"],
                "signal_date": str(candidate["signal_date"]),
                "entry_date": trade_date,
                "gross_entry_price": gross_entry,
                "entry_price": effective_entry,
                "shares": shares,
                "invested_cash": target_cash,
                "realized_cash": 0.0,
                "score": candidate.get("score"),
                "candidate_types": candidate.get("candidate_types", []),
                "holding_days": 0,
                "peak_price": gross_entry,
                "max_runup_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "partial_taken": False,
                "entry_meta": entry_meta,
                "cum_super": 0.0,
                "cum_super_peak": 0.0,
                "cum_amount": 0.0,
            }
            opened += 1

        mark_value = cash
        for symbol, pos in positions.items():
            row = row_map.get((symbol, trade_date))
            mark_price = float(row["close"]) if row is not None else float(pos["gross_entry_price"])
            mark_value += float(pos["shares"]) * mark_price
        equity_curve.append(
            {
                "date": trade_date,
                "cash": round(cash, 2),
                "equity": round(mark_value, 2),
                "open_positions": len(positions),
            }
        )
        daily_results.append(
            {
                "trade_date": trade_date,
                "opened": opened,
                "exited": exited,
                "skipped_entries": skipped,
                "open_positions": len(positions),
                "equity": round(mark_value, 2),
            }
        )

    last_date = simulation_dates[-1] if simulation_dates else resolved_replay_end
    for symbol, pos in list(positions.items()):
        row = row_map.get((symbol, last_date))
        gross_exit = float(row["close"]) if row is not None else float(pos["gross_entry_price"])
        close_position(pos, last_date, gross_exit, "window_end_force_close")
    if equity_curve:
        equity_curve[-1]["cash"] = round(cash, 2)
        equity_curve[-1]["equity"] = round(cash, 2)
        equity_curve[-1]["open_positions"] = 0

    return {
        "strategy_version": STRATEGY_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "replay_end_date": resolved_replay_end,
        "params": asdict(active_params),
        "summary": _portfolio_summary(trades, equity_curve, budget),
        "daily_screen": daily_screen,
        "daily_results": daily_results,
        "equity_curve": equity_curve,
        "trades": sorted(trades, key=lambda item: (str(item["entry_date"]), str(item["symbol"]))),
    }


def write_outputs(payload: Dict[str, Any], out_dir: str | Path, *, prefix: str) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    written = {"json": str(json_path)}
    if "items" in payload:
        csv_path = out / f"{prefix}_items.csv"
        pd.DataFrame(payload["items"]).to_csv(csv_path, index=False)
        written["items_csv"] = str(csv_path)
    if "trades" in payload:
        trades_path = out / f"{prefix}_trades.csv"
        pd.DataFrame(payload["trades"]).to_csv(trades_path, index=False)
        written["trades_csv"] = str(trades_path)
    if "equity_curve" in payload:
        equity_path = out / f"{prefix}_equity_curve.csv"
        pd.DataFrame(payload["equity_curve"]).to_csv(equity_path, index=False)
        written["equity_csv"] = str(equity_path)
    md_path = out / f"{prefix}.md"
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    written["markdown"] = str(md_path)
    return written


def _render_markdown(payload: Dict[str, Any]) -> str:
    if "items" in payload:
        lines = [
            f"# {STRATEGY_VERSION} 模拟盘计划",
            "",
            f"- 决策日：{payload.get('signal_date')}",
            f"- 计划交易日：{payload.get('planned_entry_date')}",
            f"- 预算：{payload.get('budget')}",
            f"- 目标仓位：{payload.get('target_exposure_pct')}%",
            f"- 市场状态：{payload.get('market_regime', {}).get('label')} / {payload.get('market_regime', {}).get('score')}",
            "",
            "| 排名 | 股票 | 分数 | 仓位金额 | 候选类型 | 触发价区间 | 主要理由 |",
            "|---:|---|---:|---:|---|---|---|",
        ]
        for item in payload.get("items", []):
            price_range = item.get("buy_trigger", {}).get("price_range", [])
            lines.append(
                f"| {item.get('rank')} | {item.get('name')} `{item.get('symbol')}` | {item.get('score')} | "
                f"{item.get('planned_capital')} | {','.join(item.get('candidate_types') or [])} | "
                f"{price_range} | {'；'.join(item.get('reasons') or [])} |"
            )
        return "\n".join(lines) + "\n"

    summary = payload.get("summary", {})
    lines = [
        f"# {STRATEGY_VERSION} 回测",
        "",
        f"- 信号区间：{payload.get('start_date')} ~ {payload.get('end_date')}",
        f"- 回放到：{payload.get('replay_end_date')}",
        f"- 初始资金：{summary.get('initial_budget')}",
        f"- 期末权益：{summary.get('final_equity')}",
        f"- 总收益：{summary.get('total_return_pct')}%",
        f"- 最大回撤：{summary.get('max_drawdown_pct')}%",
        f"- 交易数：{summary.get('trade_count')}",
        f"- 胜率：{summary.get('win_rate_pct')}%",
        "",
        "| 股票 | 入场 | 出场 | 收益 | 最大浮盈 | 最大回撤 | 原因 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for trade in payload.get("trades", [])[:80]:
        lines.append(
            f"| {trade.get('name')} `{trade.get('symbol')}` | {trade.get('entry_date')} | {trade.get('exit_date')} | "
            f"{trade.get('net_return_pct')}% | {trade.get('max_runup_pct')}% | {trade.get('max_drawdown_pct')}% | {trade.get('exit_reason')} |"
        )
    return "\n".join(lines) + "\n"
