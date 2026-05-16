from __future__ import annotations

import csv
import json
import math
import os
import random
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from backend.app.services.selection_strategy_v2 import resolve_selection_v2_atomic_db_path

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - optional PPO dependency
    gym = None
    spaces = None


LAB_VERSION = "intraday_evolution_lab_v0_1"
DEFAULT_OUTPUT_DIR = Path("data/selection/evolution_lab")


@dataclass(frozen=True)
class IntradayCostParams:
    buy_slippage_bp: float = 8.0
    sell_slippage_bp: float = 8.0
    round_trip_fee_bp: float = 18.0


@dataclass(frozen=True)
class IntradayStrategySpec:
    name: str
    data_tier: str = "full_l2_order_book"
    earliest_entry_time: str = "09:35:00"
    latest_entry_time: str = "14:20:00"
    max_positions: int = 4
    max_new_positions_per_day: int = 2
    position_pct: float = 0.20
    max_total_exposure_pct: float = 0.80
    min_bucket_amount: float = 8_000_000.0
    min_cum_amount: float = 60_000_000.0
    min_return_from_open_pct: float = 0.0
    max_return_from_open_pct: float = 7.8
    min_l2_main_ratio: float = 0.0
    min_l2_super_ratio: float = -0.003
    min_oib_ratio: float = -0.004
    min_cvd_ratio: float = -0.004
    min_book_imbalance: float = -0.15
    min_price_vs_vwap_pct: float = -0.8
    stop_loss_pct: float = -5.5
    take_profit_pct: float = 9.0
    trailing_activate_pct: float = 7.0
    trailing_drawdown_pct: float = -4.5
    max_holding_buckets: int = 72
    max_holding_days: int = 6
    require_order_book: bool = True


@dataclass(frozen=True)
class EvolutionConfig:
    start_date: str
    end_date: str
    budget: float = 1_000_000.0
    population_size: int = 200
    generations: int = 2
    elite_size: int = 12
    mutation_rate: float = 0.35
    seed: int = 7
    max_symbols_per_day: int = 240
    data_tier: str = "full_l2_order_book"
    train_days: int = 18
    validation_days: int = 8
    test_days: int = 8
    step_days: int = 8


@dataclass(frozen=True)
class RLRewardConfig:
    terminal_return_weight: float = 1.0
    max_drawdown_penalty_weight: float = 0.18
    step_return_weight: float = 0.08
    turnover_penalty_weight: float = 0.01
    invalid_action_penalty: float = 0.03
    idle_cash_penalty_weight: float = 0.02
    hold_winner_reward_weight: float = 0.0
    hold_winner_reward_weight: float = 0.0


@dataclass(frozen=True)
class RLTradingEnvConfig:
    budget: float = 1_000_000.0
    max_positions: int = 8
    max_position_pct: float = 0.35
    max_total_exposure_pct: float = 1.0
    min_order_cash: float = 5_000.0
    max_observation_symbols: int = 80
    reward: RLRewardConfig = RLRewardConfig()


@dataclass(frozen=True)
class RLTrainerConfig:
    start_date: str
    end_date: str
    budget: float = 1_000_000.0
    population_size: int = 48
    generations: int = 4
    elite_fraction: float = 0.20
    sigma: float = 0.65
    sigma_decay: float = 0.80
    seed: int = 7
    max_symbols_per_day: int = 80
    max_observation_symbols: int = 80


@dataclass(frozen=True)
class RLTargetPolicyTrainerConfig:
    start_date: str
    end_date: str
    budget: float = 1_000_000.0
    population_size: int = 64
    generations: int = 8
    elite_fraction: float = 0.16
    sigma: float = 0.55
    sigma_decay: float = 0.86
    seed: int = 11
    max_symbols_per_day: int = 80
    max_observation_symbols: int = 80
    hidden_size: int = 8
    target_return_pct: float = 5.0
    stop_on_target: bool = True


@dataclass(frozen=True)
class RLPPOTrainerConfig:
    start_date: str
    end_date: str
    budget: float = 1_000_000.0
    total_timesteps: int = 20_000
    learning_rate: float = 0.0003
    n_steps: int = 256
    batch_size: int = 64
    n_epochs: int = 8
    gamma: float = 0.995
    seed: int = 13
    max_symbols_per_day: int = 40
    max_observation_symbols: int = 20
    target_return_pct: float = 5.0
    feature_set: str = "full_l2_order_book"


@dataclass(frozen=True)
class TrendPortfolioPPOTrainerConfig:
    start_date: str
    end_date: str
    budget: float = 1_000_000.0
    total_timesteps: int = 60_000
    learning_rate: float = 0.00025
    n_steps: int = 512
    batch_size: int = 128
    n_epochs: int = 8
    gamma: float = 0.999
    seed: int = 29
    max_symbols_per_day: int = 80
    max_observation_symbols: int = 30
    episode_min_days: int = 10
    episode_max_days: int = 30
    target_return_pct: float = 5.0
    ent_coef: float = 0.02
    clip_range: float = 0.2


def _connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _is_mainboard_10cm_symbol(symbol: str) -> bool:
    text = str(symbol).lower()
    return text.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def _apply_buy_costs(price: float, costs: IntradayCostParams) -> float:
    return float(price) * (1.0 + (float(costs.buy_slippage_bp) + float(costs.round_trip_fee_bp) / 2.0) / 10_000.0)


def _apply_sell_costs(price: float, costs: IntradayCostParams) -> float:
    return float(price) * (1.0 - (float(costs.sell_slippage_bp) + float(costs.round_trip_fee_bp) / 2.0) / 10_000.0)


def catalog_intraday_data(*, db_path: Optional[str] = None) -> Dict[str, Any]:
    path = db_path or resolve_selection_v2_atomic_db_path()
    tables = [
        "atomic_trade_5m",
        "atomic_order_5m",
        "atomic_book_state_5m",
        "atomic_limit_state_5m",
        "atomic_trade_daily",
        "atomic_order_daily",
    ]
    out: Dict[str, Any] = {
        "lab_version": LAB_VERSION,
        "atomic_db_path": path,
        "tables": {},
        "recommended_windows": {
            "full_l2_order_book": {"start_date": "2026-03-02", "reason": "5m trade/order/book state all available"},
            "weak_trade_l2": {"start_date": "2025-01-02", "reason": "trade/limit 5m available before order/book coverage"},
        },
        "raw_extract_policy": "not_required_for_normal_research; only for rebuild/audit/finer_tick_studies",
        "universe_policy": "mainboard_10cm_symbols_ranked_by_previous_trade_date_amount",
    }
    with _connect_ro(path) as conn:
        for table in tables:
            if not _table_exists(conn, table):
                out["tables"][table] = {"exists": False}
                continue
            cols = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            date_col = "trade_date" if "trade_date" in cols else None
            if not date_col:
                out["tables"][table] = {"exists": True, "columns": cols}
                continue
            first = conn.execute(f"SELECT {date_col} FROM {table} ORDER BY {date_col} ASC LIMIT 1").fetchone()
            last = conn.execute(f"SELECT {date_col} FROM {table} ORDER BY {date_col} DESC LIMIT 1").fetchone()
            out["tables"][table] = {
                "exists": True,
                "start_date": str(first[0]) if first else None,
                "end_date": str(last[0]) if last else None,
                "columns": cols,
            }
    return out


def _trade_dates(start_date: str, end_date: str, *, db_path: Optional[str] = None) -> List[str]:
    path = db_path or resolve_selection_v2_atomic_db_path()
    with _connect_ro(path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_5m
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
    return [str(row[0]) for row in rows]


def select_replay_universe(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    max_symbols_per_day: int = 240,
    symbols: Optional[Sequence[str]] = None,
) -> List[str]:
    if symbols:
        return sorted({str(symbol).strip().lower() for symbol in symbols if str(symbol).strip()})
    by_date = select_replay_universe_by_date(
        start_date,
        end_date,
        db_path=db_path,
        max_symbols_per_day=max_symbols_per_day,
    )
    return sorted({symbol for items in by_date.values() for symbol in items})


def select_replay_universe_by_date(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    max_symbols_per_day: int = 240,
) -> Dict[str, List[str]]:
    path = db_path or resolve_selection_v2_atomic_db_path()
    with _connect_ro(path) as conn:
        rows = conn.execute(
            """
            SELECT trade_date, symbol
            FROM (
                SELECT
                    lower(cur.symbol) AS symbol,
                    cur.trade_date,
                    prev.total_amount AS prior_total_amount,
                    ROW_NUMBER() OVER (PARTITION BY cur.trade_date ORDER BY prev.total_amount DESC) AS rn
                FROM atomic_trade_daily AS cur
                JOIN atomic_trade_daily AS prev
                  ON prev.symbol = cur.symbol
                 AND prev.trade_date = (
                    SELECT max(p2.trade_date)
                    FROM atomic_trade_daily AS p2
                    WHERE p2.symbol = cur.symbol
                      AND p2.trade_date < cur.trade_date
                 )
                WHERE cur.trade_date >= ?
                  AND cur.trade_date <= ?
                  AND (
                    lower(cur.symbol) LIKE 'sh600%'
                    OR lower(cur.symbol) LIKE 'sh601%'
                    OR lower(cur.symbol) LIKE 'sh603%'
                    OR lower(cur.symbol) LIKE 'sh605%'
                    OR lower(cur.symbol) LIKE 'sz000%'
                    OR lower(cur.symbol) LIKE 'sz001%'
                    OR lower(cur.symbol) LIKE 'sz002%'
                    OR lower(cur.symbol) LIKE 'sz003%'
                  )
            )
            WHERE rn <= ?
            """,
            (start_date, end_date, int(max_symbols_per_day)),
        ).fetchall()
    out: Dict[str, List[str]] = {}
    for row in rows:
        out.setdefault(str(row[0]), []).append(str(row[1]).lower())
    return {date: sorted(set(items)) for date, items in out.items()}


def load_intraday_panel(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    max_symbols_per_day: int = 240,
) -> pd.DataFrame:
    path = db_path or resolve_selection_v2_atomic_db_path()
    universe_by_date: Optional[Dict[str, List[str]]] = None
    if symbols:
        selected_symbols = select_replay_universe(
            start_date,
            end_date,
            db_path=path,
            max_symbols_per_day=max_symbols_per_day,
            symbols=symbols,
        )
    else:
        universe_by_date = select_replay_universe_by_date(
            start_date,
            end_date,
            db_path=path,
            max_symbols_per_day=max_symbols_per_day,
        )
        selected_symbols = sorted({symbol for items in universe_by_date.values() for symbol in items})
    if not selected_symbols:
        return pd.DataFrame()

    placeholders = ",".join("?" for _ in selected_symbols)
    params: List[Any] = [start_date, end_date, *selected_symbols]
    with _connect_ro(path) as conn:
        has_order = _table_exists(conn, "atomic_order_5m")
        has_book = _table_exists(conn, "atomic_book_state_5m")
        has_limit = _table_exists(conn, "atomic_limit_state_5m")
        order_select = (
            """
            o.add_buy_amount,
            o.add_sell_amount,
            o.cancel_buy_amount,
            o.cancel_sell_amount,
            o.cvd_delta_amount,
            o.oib_delta_amount,
            o.order_event_count,
            """
            if has_order
            else """
            0.0 AS add_buy_amount,
            0.0 AS add_sell_amount,
            0.0 AS cancel_buy_amount,
            0.0 AS cancel_sell_amount,
            0.0 AS cvd_delta_amount,
            0.0 AS oib_delta_amount,
            0.0 AS order_event_count,
            """
        )
        order_join = "LEFT JOIN atomic_order_5m AS o ON o.symbol = t.symbol AND o.bucket_start = t.bucket_start" if has_order else ""
        book_select = (
            """
            b.end_bid_resting_amount,
            b.end_ask_resting_amount,
            b.top5_bid_amount,
            b.top5_ask_amount,
            b.book_imbalance_ratio,
            b.book_depth_ratio,
            b.book_state_label,
            """
            if has_book
            else """
            0.0 AS end_bid_resting_amount,
            0.0 AS end_ask_resting_amount,
            0.0 AS top5_bid_amount,
            0.0 AS top5_ask_amount,
            0.0 AS book_imbalance_ratio,
            0.0 AS book_depth_ratio,
            '' AS book_state_label,
            """
        )
        book_join = "LEFT JOIN atomic_book_state_5m AS b ON b.symbol = t.symbol AND b.bucket_start = t.bucket_start" if has_book else ""
        limit_select = (
            """
            l.risk_flag_type,
            l.prev_close,
            l.up_limit_price,
            l.down_limit_price,
            l.touch_limit_up,
            l.touch_limit_down,
            l.is_limit_up_close_5m,
            l.is_limit_down_close_5m,
            l.near_limit_up_ratio,
            l.near_limit_down_ratio,
            l.state_label_5m
            """
            if has_limit
            else """
            'normal' AS risk_flag_type,
            0.0 AS prev_close,
            0.0 AS up_limit_price,
            0.0 AS down_limit_price,
            0 AS touch_limit_up,
            0 AS touch_limit_down,
            0 AS is_limit_up_close_5m,
            0 AS is_limit_down_close_5m,
            0.0 AS near_limit_up_ratio,
            0.0 AS near_limit_down_ratio,
            '' AS state_label_5m
            """
        )
        limit_join = "LEFT JOIN atomic_limit_state_5m AS l ON l.symbol = t.symbol AND l.bucket_start = t.bucket_start" if has_limit else ""
        df = pd.read_sql_query(
            f"""
            SELECT
                lower(t.symbol) AS symbol,
                t.trade_date,
                t.bucket_start,
                substr(t.bucket_start, 12, 8) AS bucket_time,
                t.open,
                t.high,
                t.low,
                t.close,
                t.total_amount,
                t.total_volume,
                t.trade_count,
                t.l2_main_net_amount,
                t.l2_super_net_amount,
                t.l1_main_net_amount,
                t.l1_super_net_amount,
                {order_select}
                {book_select}
                {limit_select}
            FROM atomic_trade_5m AS t
            {order_join}
            {book_join}
            {limit_join}
            WHERE t.trade_date >= ?
              AND t.trade_date <= ?
              AND lower(t.symbol) IN ({placeholders})
            ORDER BY t.trade_date ASC, t.bucket_start ASC, lower(t.symbol) ASC
            """,
            conn,
            params=params,
        )
    if df.empty:
        return df
    if universe_by_date is not None:
        eligible_pairs = {(date, symbol) for date, items in universe_by_date.items() for symbol in items}
        df = df[df.apply(lambda row: (str(row["trade_date"]), str(row["symbol"])) in eligible_pairs, axis=1)].copy()
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
        "l2_main_net_amount",
        "l2_super_net_amount",
        "l1_main_net_amount",
        "l1_super_net_amount",
        "add_buy_amount",
        "add_sell_amount",
        "cancel_buy_amount",
        "cancel_sell_amount",
        "cvd_delta_amount",
        "oib_delta_amount",
        "order_event_count",
        "end_bid_resting_amount",
        "end_ask_resting_amount",
        "top5_bid_amount",
        "top5_ask_amount",
        "book_imbalance_ratio",
        "book_depth_ratio",
        "prev_close",
        "up_limit_price",
        "down_limit_price",
        "touch_limit_up",
        "touch_limit_down",
        "is_limit_up_close_5m",
        "is_limit_down_close_5m",
        "near_limit_up_ratio",
        "near_limit_down_ratio",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["risk_flag_type"] = df.get("risk_flag_type", "normal").fillna("normal").astype(str)
    df["book_state_label"] = df.get("book_state_label", "").fillna("").astype(str)
    df["state_label_5m"] = df.get("state_label_5m", "").fillna("").astype(str)
    return _add_point_in_time_features(df)


def _daily_select_expr(alias: str, available_cols: set[str], column: str, default_sql: str = "0.0") -> str:
    if column in available_cols:
        return f"{alias}.{column} AS {column}"
    return f"{default_sql} AS {column}"


def load_trend_daily_panel(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    max_symbols_per_day: int = 120,
    lookback_calendar_days: int = 120,
) -> pd.DataFrame:
    from backend.app.services.selection_strategy_v2 import compute_v2_metrics

    path = db_path or resolve_selection_v2_atomic_db_path()
    lookback_start = (pd.Timestamp(start_date) - pd.Timedelta(days=int(lookback_calendar_days))).strftime("%Y-%m-%d")
    universe_by_date: Optional[Dict[str, List[str]]] = None
    if symbols:
        selected_symbols = sorted({str(symbol).strip().lower() for symbol in symbols if str(symbol).strip()})
    else:
        universe_by_date = select_replay_universe_by_date(
            start_date,
            end_date,
            db_path=path,
            max_symbols_per_day=max_symbols_per_day,
        )
        selected_symbols = sorted({symbol for items in universe_by_date.values() for symbol in items})
    if not selected_symbols:
        return pd.DataFrame()

    placeholders = ",".join("?" for _ in selected_symbols)
    params: List[Any] = [lookback_start, end_date, *selected_symbols]
    with _connect_ro(path) as conn:
        trade_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(atomic_trade_daily)").fetchall()}
        has_order = _table_exists(conn, "atomic_order_daily")
        order_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(atomic_order_daily)").fetchall()} if has_order else set()
        has_limit = _table_exists(conn, "atomic_limit_state_daily")
        limit_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(atomic_limit_state_daily)").fetchall()} if has_limit else set()
        trade_select = [
            _daily_select_expr("t", trade_cols, "open"),
            _daily_select_expr("t", trade_cols, "high"),
            _daily_select_expr("t", trade_cols, "low"),
            _daily_select_expr("t", trade_cols, "close"),
            _daily_select_expr("t", trade_cols, "total_amount"),
            _daily_select_expr("t", trade_cols, "total_volume"),
            _daily_select_expr("t", trade_cols, "trade_count"),
            _daily_select_expr("t", trade_cols, "l1_main_net_amount"),
            _daily_select_expr("t", trade_cols, "l2_main_net_amount"),
            _daily_select_expr("t", trade_cols, "l1_super_net_amount"),
            _daily_select_expr("t", trade_cols, "l2_super_net_amount"),
            _daily_select_expr("t", trade_cols, "l2_buy_ratio"),
            _daily_select_expr("t", trade_cols, "l2_sell_ratio"),
            _daily_select_expr("t", trade_cols, "l1_buy_ratio"),
            _daily_select_expr("t", trade_cols, "l1_sell_ratio"),
            _daily_select_expr("t", trade_cols, "positive_l2_net_bar_count"),
            _daily_select_expr("t", trade_cols, "negative_l2_net_bar_count"),
        ]
        order_select = [
            _daily_select_expr("o", order_cols, "add_buy_amount"),
            _daily_select_expr("o", order_cols, "add_sell_amount"),
            _daily_select_expr("o", order_cols, "cancel_buy_amount"),
            _daily_select_expr("o", order_cols, "cancel_sell_amount"),
            _daily_select_expr("o", order_cols, "cvd_delta_amount"),
            _daily_select_expr("o", order_cols, "oib_delta_amount"),
            _daily_select_expr("o", order_cols, "positive_oib_bar_count"),
            _daily_select_expr("o", order_cols, "negative_oib_bar_count"),
            _daily_select_expr("o", order_cols, "positive_cvd_bar_count"),
            _daily_select_expr("o", order_cols, "negative_cvd_bar_count"),
            _daily_select_expr("o", order_cols, "buy_support_ratio"),
            _daily_select_expr("o", order_cols, "sell_pressure_ratio"),
            _daily_select_expr("o", order_cols, "order_event_count"),
        ]
        limit_select = [
            _daily_select_expr("l", limit_cols, "risk_flag_type", "'normal'"),
            _daily_select_expr("l", limit_cols, "prev_close"),
            _daily_select_expr("l", limit_cols, "up_limit_price"),
            _daily_select_expr("l", limit_cols, "down_limit_price"),
            _daily_select_expr("l", limit_cols, "touch_limit_up"),
            _daily_select_expr("l", limit_cols, "touch_limit_down"),
            _daily_select_expr("l", limit_cols, "is_limit_up_close"),
            _daily_select_expr("l", limit_cols, "is_limit_down_close"),
            _daily_select_expr("l", limit_cols, "limit_state_label", "''"),
        ]
        order_join = "LEFT JOIN atomic_order_daily AS o ON o.symbol = t.symbol AND o.trade_date = t.trade_date" if has_order else ""
        limit_join = "LEFT JOIN atomic_limit_state_daily AS l ON l.symbol = t.symbol AND l.trade_date = t.trade_date" if has_limit else ""
        df = pd.read_sql_query(
            f"""
            SELECT
                lower(t.symbol) AS symbol,
                t.trade_date,
                {", ".join(trade_select + order_select + limit_select)}
            FROM atomic_trade_daily AS t
            {order_join}
            {limit_join}
            WHERE t.trade_date >= ?
              AND t.trade_date <= ?
              AND lower(t.symbol) IN ({placeholders})
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
            """,
            conn,
            params=params,
        )
    if df.empty:
        return df
    numeric_cols = [col for col in df.columns if col not in {"symbol", "trade_date", "risk_flag_type", "limit_state_label"}]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["risk_flag_type"] = df.get("risk_flag_type", "normal").fillna("normal").astype(str)
    df["limit_state_label"] = df.get("limit_state_label", "").fillna("").astype(str)
    metrics = compute_v2_metrics(df)
    metrics = metrics[(metrics["trade_date"] >= start_date) & (metrics["trade_date"] <= end_date)].copy()
    if metrics.empty:
        return metrics
    if universe_by_date is not None:
        eligible_pairs = {(date, symbol) for date, items in universe_by_date.items() for symbol in items}
        metrics = metrics[metrics.apply(lambda row: (str(row["trade_date"]), str(row["symbol"])) in eligible_pairs, axis=1)].copy()
    if metrics.empty:
        return metrics
    for col in metrics.columns:
        if col not in {"symbol", "trade_date", "risk_flag_type", "limit_state_label"}:
            metrics[col] = pd.to_numeric(metrics[col], errors="coerce").fillna(0.0)
    return metrics.sort_values(["trade_date", "symbol"]).reset_index(drop=True)


def _add_point_in_time_features(df: pd.DataFrame) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for (_, _), group in df.groupby(["symbol", "trade_date"], sort=False):
        g = group.sort_values("bucket_start").copy()
        g["bar_index"] = range(len(g))
        open_price = float(g["open"].iloc[0] or 0.0)
        cumulative_amount = g["total_amount"].cumsum()
        cumulative_volume = g["total_volume"].cumsum().replace(0, pd.NA)
        cumulative_turnover = (g["close"] * g["total_volume"]).cumsum()
        g["cum_amount"] = cumulative_amount
        g["cum_l2_main_net_amount"] = g["l2_main_net_amount"].cumsum()
        g["cum_l2_super_net_amount"] = g["l2_super_net_amount"].cumsum()
        g["cum_oib_delta_amount"] = g["oib_delta_amount"].cumsum()
        g["cum_cvd_delta_amount"] = g["cvd_delta_amount"].cumsum()
        g["vwap"] = (cumulative_turnover / cumulative_volume).fillna(g["close"])
        g["return_from_open_pct"] = ((g["close"] / open_price) - 1.0) * 100.0 if open_price > 0 else 0.0
        g["price_vs_vwap_pct"] = ((g["close"] / g["vwap"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        g["l2_main_net_ratio"] = (g["l2_main_net_amount"] / g["total_amount"].replace(0, pd.NA)).fillna(0.0)
        g["l2_super_net_ratio"] = (g["l2_super_net_amount"] / g["total_amount"].replace(0, pd.NA)).fillna(0.0)
        g["oib_ratio"] = (g["oib_delta_amount"] / g["total_amount"].replace(0, pd.NA)).fillna(0.0)
        g["cvd_ratio"] = (g["cvd_delta_amount"] / g["total_amount"].replace(0, pd.NA)).fillna(0.0)
        g["cum_l2_main_ratio"] = (g["cum_l2_main_net_amount"] / g["cum_amount"].replace(0, pd.NA)).fillna(0.0)
        g["cum_l2_super_ratio"] = (g["cum_l2_super_net_amount"] / g["cum_amount"].replace(0, pd.NA)).fillna(0.0)
        g["cum_oib_ratio"] = (g["cum_oib_delta_amount"] / g["cum_amount"].replace(0, pd.NA)).fillna(0.0)
        g["cum_cvd_ratio"] = (g["cum_cvd_delta_amount"] / g["cum_amount"].replace(0, pd.NA)).fillna(0.0)
        g["rolling3_l2_main_ratio"] = (
            g["l2_main_net_amount"].rolling(3, min_periods=1).sum()
            / g["total_amount"].rolling(3, min_periods=1).sum().replace(0, pd.NA)
        ).fillna(0.0)
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    out["has_order_book"] = (
        out[["add_buy_amount", "add_sell_amount", "cancel_buy_amount", "cancel_sell_amount", "end_bid_resting_amount", "end_ask_resting_amount"]]
        .abs()
        .sum(axis=1)
        .gt(0)
    )
    out["data_tier"] = out["has_order_book"].map(lambda value: "full_l2_order_book" if bool(value) else "weak_trade_l2")
    return out.sort_values(["trade_date", "bucket_start", "symbol"]).reset_index(drop=True)


def _row_map(panel: pd.DataFrame) -> Dict[Tuple[str, str], pd.Series]:
    return {(str(row["symbol"]), str(row["bucket_start"])): row for _, row in panel.iterrows()}


def _next_bucket_map(panel: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    out: Dict[Tuple[str, str], str] = {}
    for symbol, group in panel.groupby("symbol", sort=False):
        buckets = [str(v) for v in group.sort_values("bucket_start")["bucket_start"].tolist()]
        for idx, bucket in enumerate(buckets[:-1]):
            out[(str(symbol), bucket)] = buckets[idx + 1]
    return out


def _portfolio_summary(
    trades: Sequence[Dict[str, Any]],
    equity_curve: Sequence[Dict[str, Any]],
    initial_budget: float,
    *,
    planned_entries: int = 0,
    filled_entries: int = 0,
) -> Dict[str, Any]:
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else float(initial_budget)
    equity = pd.Series([float(item["equity"]) for item in equity_curve]) if equity_curve else pd.Series(dtype=float)
    max_drawdown = float(((equity / equity.cummax()) - 1.0).min() * 100.0) if not equity.empty else 0.0
    returns = pd.Series([float(trade.get("net_return_pct") or 0.0) for trade in trades])
    pnl = pd.Series([float(trade.get("pnl_cash") or 0.0) for trade in trades])
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    gross_profit = float(pnl[pnl > 0].sum()) if not pnl.empty else 0.0
    gross_loss = float(pnl[pnl < 0].sum()) if not pnl.empty else 0.0
    profit_factor = 999.0 if gross_loss == 0 and gross_profit > 0 else (gross_profit / abs(gross_loss) if gross_loss < 0 else 0.0)
    return {
        "initial_budget": round(float(initial_budget), 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / float(initial_budget) - 1.0) * 100.0, 2) if initial_budget else 0.0,
        "max_drawdown_pct": round(max_drawdown, 2),
        "trade_count": int(len(trades)),
        "win_rate_pct": round(float((returns > 0).mean() * 100.0), 2) if not returns.empty else 0.0,
        "avg_net_return_pct": round(float(returns.mean()), 2) if not returns.empty else 0.0,
        "median_net_return_pct": round(float(returns.median()), 2) if not returns.empty else 0.0,
        "max_net_return_pct": round(float(returns.max()), 2) if not returns.empty else 0.0,
        "min_net_return_pct": round(float(returns.min()), 2) if not returns.empty else 0.0,
        "profit_factor": round(float(profit_factor), 3),
        "planned_entries": int(planned_entries),
        "filled_entries": int(filled_entries),
        "entry_fill_rate_pct": round((filled_entries / planned_entries) * 100.0, 2) if planned_entries else 0.0,
        "big_loss_le_-7pct": int((returns <= -7.0).sum()) if not returns.empty else 0,
        "big_winner_gt_10pct": int((returns > 10.0).sum()) if not returns.empty else 0,
    }


class RLTradingEnv:
    """
    Gym-style 5m A-share trading environment.

    The environment owns all market rules and account state. A learner only
    supplies actions for the next step, so no strategy DSL is embedded here.
    """

    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        config: Optional[RLTradingEnvConfig] = None,
        costs: Optional[IntradayCostParams] = None,
    ) -> None:
        self.panel = panel.sort_values(["bucket_start", "symbol"]).reset_index(drop=True)
        self.config = config or RLTradingEnvConfig()
        self.costs = costs or IntradayCostParams()
        self.row_by_symbol_bucket = _row_map(self.panel)
        self.buckets = [str(v) for v in sorted(self.panel["bucket_start"].unique())]
        self.panel_by_bucket = {str(k): g for k, g in self.panel.groupby("bucket_start", sort=False)}
        self.reset()

    def reset(self) -> Dict[str, Any]:
        self.index = 0
        self.cash = float(self.config.budget)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.actions_log: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.prev_equity = float(self.config.budget)
        self.peak_equity = float(self.config.budget)
        self.max_drawdown_pct = 0.0
        return self._observation()

    def step(self, actions: Sequence[Dict[str, Any]] | Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        if self.index >= len(self.buckets):
            return self._observation(), 0.0, True, {"reason": "episode_already_done"}

        decision_bucket = self.buckets[self.index]
        if self.index + 1 >= len(self.buckets):
            equity = self._mark_equity(decision_bucket)
            self.equity_curve.append(
                {
                    "bucket_start": decision_bucket,
                    "trade_date": decision_bucket[:10],
                    "cash": round(self.cash, 2),
                    "equity": round(equity, 2),
                    "open_positions": len(self.positions),
                    "drawdown_pct": round(self.max_drawdown_pct, 4),
                }
            )
            self.index = len(self.buckets)
            reward = self._reward(equity=equity, step_return=0.0, turnover_cash=0.0, invalid_count=0, done=True)
            return self._observation(), reward, True, {"bucket_start": decision_bucket, "equity": round(equity, 2), "reason": "no_next_bucket"}

        execution_bucket = self.buckets[self.index + 1]
        rows = self.panel_by_bucket.get(execution_bucket, pd.DataFrame())
        invalid_count = 0
        turnover_cash = 0.0
        for action in self._normalize_actions(actions):
            ok, cash_delta = self._execute_action(action, decision_bucket, execution_bucket)
            turnover_cash += abs(float(cash_delta))
            if not ok:
                invalid_count += 1

        equity = self._mark_equity(execution_bucket)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown_pct = ((equity / self.peak_equity) - 1.0) * 100.0 if self.peak_equity else 0.0
        self.max_drawdown_pct = min(self.max_drawdown_pct, drawdown_pct)
        step_return = (equity / self.prev_equity - 1.0) if self.prev_equity else 0.0
        self.prev_equity = equity
        self.equity_curve.append(
            {
                "bucket_start": execution_bucket,
                "trade_date": execution_bucket[:10],
                "decision_bucket": decision_bucket,
                "cash": round(self.cash, 2),
                "equity": round(equity, 2),
                "open_positions": len(self.positions),
                "drawdown_pct": round(drawdown_pct, 4),
            }
        )

        self.index += 1
        done = self.index >= len(self.buckets)
        if done and self.buckets:
            final_bucket = self.buckets[-1]
            equity = self._mark_equity(final_bucket)
            if self.equity_curve:
                self.equity_curve[-1]["cash"] = round(self.cash, 2)
                self.equity_curve[-1]["equity"] = round(equity, 2)
                self.equity_curve[-1]["open_positions"] = len(self.positions)

        reward = self._reward(
            equity=equity,
            step_return=step_return,
            turnover_cash=turnover_cash,
            invalid_count=invalid_count,
            done=done,
        )
        info = {
            "decision_bucket": decision_bucket,
            "bucket_start": execution_bucket,
            "rows": int(len(rows)),
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "open_positions": len(self.positions),
            "invalid_actions": invalid_count,
            "turnover_cash": round(turnover_cash, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
        }
        return self._observation(), reward, done, info

    def summary(self) -> Dict[str, Any]:
        final_equity = float(self.equity_curve[-1]["equity"]) if self.equity_curve else float(self.config.budget)
        return {
            "initial_budget": round(float(self.config.budget), 2),
            "final_equity": round(final_equity, 2),
            "total_return_pct": round((final_equity / float(self.config.budget) - 1.0) * 100.0, 2) if self.config.budget else 0.0,
            "max_drawdown_pct": round(float(self.max_drawdown_pct), 2),
            "trade_count": int(len(self.trades)),
            "open_positions": int(len(self.positions)),
            "cash": round(float(self.cash), 2),
        }

    def _normalize_actions(self, actions: Sequence[Dict[str, Any]] | Dict[str, Any] | None) -> List[Dict[str, Any]]:
        if actions is None:
            return []
        if isinstance(actions, dict):
            return [actions]
        return [item for item in actions if isinstance(item, dict)]

    def _observation(self) -> Dict[str, Any]:
        bucket = self.buckets[self.index] if self.index < len(self.buckets) else (self.buckets[-1] if self.buckets else None)
        rows = self.panel_by_bucket.get(bucket, pd.DataFrame()) if bucket else pd.DataFrame()
        market_rows = []
        if rows is not None and not rows.empty:
            ranked = rows.sort_values("total_amount", ascending=False).head(int(self.config.max_observation_symbols))
            for _, row in ranked.iterrows():
                market_rows.append(
                    {
                        "symbol": str(row["symbol"]),
                        "trade_date": str(row["trade_date"]),
                        "bucket_start": str(row["bucket_start"]),
                        "bucket_time": str(row.get("bucket_time") or ""),
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": _safe_float(row.get("close")),
                        "total_amount": _safe_float(row.get("total_amount")),
                        "cum_amount": _safe_float(row.get("cum_amount")),
                        "return_from_open_pct": _safe_float(row.get("return_from_open_pct")),
                        "l2_main_net_ratio": _safe_float(row.get("l2_main_net_ratio")),
                        "l2_super_net_ratio": _safe_float(row.get("l2_super_net_ratio")),
                        "oib_ratio": _safe_float(row.get("oib_ratio")),
                        "cvd_ratio": _safe_float(row.get("cvd_ratio")),
                        "book_imbalance_ratio": _safe_float(row.get("book_imbalance_ratio")),
                        "price_vs_vwap_pct": _safe_float(row.get("price_vs_vwap_pct")),
                        "is_buy_blocked": _is_blocked_for_buy(row),
                        "is_sell_blocked": _is_blocked_for_sell(row),
                    }
                )
        positions = []
        for symbol, pos in sorted(self.positions.items()):
            row = self.row_by_symbol_bucket.get((symbol, bucket)) if bucket else None
            mark_price = _safe_float(row.get("close")) if row is not None else _safe_float(pos.get("gross_entry_price"))
            entry = _safe_float(pos.get("gross_entry_price"))
            positions.append(
                {
                    "symbol": symbol,
                    "entry_date": str(pos.get("entry_date")),
                    "shares": _safe_float(pos.get("shares")),
                    "market_value": round(_safe_float(pos.get("shares")) * mark_price, 2),
                    "cost_cash": round(_safe_float(pos.get("cost_cash")), 2),
                    "unrealized_return_pct": round(((mark_price / entry) - 1.0) * 100.0, 4) if entry else 0.0,
                    "can_sell": bool(row is not None and str(row.get("trade_date")) != str(pos.get("entry_date")) and not _is_blocked_for_sell(row)),
                }
            )
        equity = self._mark_equity(bucket) if bucket else float(self.config.budget)
        return {
            "bucket_start": bucket,
            "step_index": self.index,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "positions": positions,
            "market": market_rows,
        }

    def _execute_action(self, action: Dict[str, Any], decision_bucket: str, execution_bucket: str) -> Tuple[bool, float]:
        action_type = str(action.get("type") or "hold").lower()
        if action_type in {"hold", "skip", "noop"}:
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": execution_bucket, "action": "hold"})
            return True, 0.0
        symbol = str(action.get("symbol") or "").lower()
        if not symbol:
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": execution_bucket, "action": action_type, "reason": "missing_symbol"})
            return False, 0.0
        if action_type == "buy":
            cash_fraction = _clip(_safe_float(action.get("cash_fraction"), 0.0), 0.0, 1.0)
            cash_amount = _safe_float(action.get("cash_amount"), 0.0)
            if cash_amount <= 0:
                cash_amount = self.cash * cash_fraction
            return self._buy_cash(symbol, execution_bucket, cash_amount, str(action.get("reason") or "agent_buy"), decision_bucket=decision_bucket)
        if action_type == "sell":
            fraction = _clip(_safe_float(action.get("fraction"), 1.0), 0.0, 1.0)
            return self._sell_fraction(symbol, execution_bucket, fraction, str(action.get("reason") or "agent_sell"), decision_bucket=decision_bucket)
        return False, 0.0

    def _buy_cash(self, symbol: str, bucket: str, cash_amount: float, reason: str, *, decision_bucket: Optional[str] = None) -> Tuple[bool, float]:
        row = self.row_by_symbol_bucket.get((symbol, bucket))
        if row is None or _is_blocked_for_buy(row):
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "buy_rejected", "reason": "not_buyable"})
            return False, 0.0
        if symbol not in self.positions and len(self.positions) >= int(self.config.max_positions):
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "buy_rejected", "reason": "max_positions"})
            return False, 0.0
        gross_price = _safe_float(row.get("open"))
        if gross_price <= 0:
            return False, 0.0
        equity = self._mark_equity(bucket)
        current_symbol_value = self._position_market_value(symbol, bucket)
        current_total_exposure = sum(self._position_market_value(item, bucket) for item in self.positions)
        symbol_room = max(0.0, equity * float(self.config.max_position_pct) - current_symbol_value)
        exposure_room = max(0.0, equity * float(self.config.max_total_exposure_pct) - current_total_exposure)
        target_cash = min(float(cash_amount), self.cash, symbol_room, exposure_room)
        if target_cash < float(self.config.min_order_cash):
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "buy_rejected", "reason": "order_too_small"})
            return False, 0.0
        effective_price = _apply_buy_costs(gross_price, self.costs)
        shares = target_cash / effective_price
        self.cash -= target_cash
        pos = self.positions.get(symbol)
        if pos:
            old_shares = _safe_float(pos.get("shares"))
            old_cost = _safe_float(pos.get("cost_cash"))
            new_cost = old_cost + target_cash
            new_shares = old_shares + shares
            pos["shares"] = new_shares
            pos["cost_cash"] = new_cost
            pos["gross_entry_price"] = new_cost / new_shares if new_shares else gross_price
            pos["last_add_bucket"] = bucket
        else:
            self.positions[symbol] = {
                "symbol": symbol,
                "entry_bucket": bucket,
                "entry_date": str(row["trade_date"]),
                "gross_entry_price": gross_price,
                "shares": shares,
                "cost_cash": target_cash,
                "realized_cash": 0.0,
            }
        self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "buy", "cash": round(target_cash, 2), "reason": reason})
        return True, target_cash

    def _sell_fraction(self, symbol: str, bucket: str, fraction: float, reason: str, *, decision_bucket: Optional[str] = None) -> Tuple[bool, float]:
        pos = self.positions.get(symbol)
        row = self.row_by_symbol_bucket.get((symbol, bucket))
        if pos is None or row is None:
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "sell_rejected", "reason": "missing_position_or_row"})
            return False, 0.0
        if str(row.get("trade_date")) == str(pos.get("entry_date")):
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "sell_rejected", "reason": "t1_locked"})
            return False, 0.0
        if _is_blocked_for_sell(row):
            self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "sell_rejected", "reason": "sell_blocked"})
            return False, 0.0
        sell_fraction = _clip(float(fraction), 0.0, 1.0)
        shares = _safe_float(pos.get("shares")) * sell_fraction
        if shares <= 0:
            return False, 0.0
        gross_price = _safe_float(row.get("open"))
        if gross_price <= 0:
            return False, 0.0
        proceeds = shares * _apply_sell_costs(gross_price, self.costs)
        cost_basis = _safe_float(pos.get("cost_cash")) * sell_fraction
        self.cash += proceeds
        remaining_shares = _safe_float(pos.get("shares")) - shares
        remaining_cost = _safe_float(pos.get("cost_cash")) - cost_basis
        self.trades.append(
            {
                "symbol": symbol,
                "entry_bucket": pos.get("entry_bucket"),
                "entry_date": pos.get("entry_date"),
                "exit_bucket": bucket,
                "exit_date": str(row.get("trade_date")),
                "gross_entry_price": round(_safe_float(pos.get("gross_entry_price")), 4),
                "gross_exit_price": round(gross_price, 4),
                "sold_fraction": round(sell_fraction, 4),
                "cost_cash": round(cost_basis, 2),
                "realized_cash": round(proceeds, 2),
                "pnl_cash": round(proceeds - cost_basis, 2),
                "net_return_pct": round((proceeds / cost_basis - 1.0) * 100.0, 4) if cost_basis else 0.0,
                "exit_reason": reason,
            }
        )
        if remaining_shares <= 1e-9 or remaining_cost <= float(self.config.min_order_cash):
            self.positions.pop(symbol, None)
        else:
            pos["shares"] = remaining_shares
            pos["cost_cash"] = remaining_cost
        self.actions_log.append({"decision_bucket": decision_bucket, "bucket_start": bucket, "symbol": symbol, "action": "sell", "fraction": round(sell_fraction, 4), "reason": reason})
        return True, proceeds

    def _position_market_value(self, symbol: str, bucket: str) -> float:
        pos = self.positions.get(symbol)
        if not pos:
            return 0.0
        row = self.row_by_symbol_bucket.get((symbol, bucket))
        mark_price = _safe_float(row.get("close")) if row is not None else _safe_float(pos.get("gross_entry_price"))
        return _safe_float(pos.get("shares")) * mark_price

    def _mark_equity(self, bucket: Optional[str]) -> float:
        equity = float(self.cash)
        if bucket is None:
            return equity
        for symbol in self.positions:
            equity += self._position_market_value(symbol, bucket)
        return equity

    def _reward(self, *, equity: float, step_return: float, turnover_cash: float, invalid_count: int, done: bool) -> float:
        reward_cfg = self.config.reward
        reward = float(reward_cfg.step_return_weight) * float(step_return)
        reward -= float(reward_cfg.turnover_penalty_weight) * (float(turnover_cash) / max(float(self.config.budget), 1.0))
        reward -= float(reward_cfg.invalid_action_penalty) * float(invalid_count)
        cash_ratio = _clip(float(self.cash) / max(float(equity), 1.0), 0.0, 1.0)
        reward -= float(reward_cfg.idle_cash_penalty_weight) * max(0.0, cash_ratio - 0.35) / 4096.0
        if done:
            terminal_return = (float(equity) / float(self.config.budget) - 1.0) if self.config.budget else 0.0
            drawdown_penalty = abs(float(self.max_drawdown_pct)) / 100.0
            reward += float(reward_cfg.terminal_return_weight) * terminal_return
            reward -= float(reward_cfg.max_drawdown_penalty_weight) * drawdown_penalty
        return float(reward)


def run_rl_random_agent_smoke(
    start_date: str,
    end_date: str,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    budget: float = 1_000_000.0,
    max_symbols_per_day: int = 80,
    seed: int = 7,
) -> Dict[str, Any]:
    panel = load_intraday_panel(
        start_date,
        end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=max_symbols_per_day,
    )
    env = RLTradingEnv(panel, config=RLTradingEnvConfig(budget=budget, max_observation_symbols=max_symbols_per_day))
    rng = random.Random(int(seed))
    obs = env.reset()
    done = False
    total_reward = 0.0
    steps = 0
    while not done:
        actions: List[Dict[str, Any]] = []
        positions = obs.get("positions") or []
        market = obs.get("market") or []
        sellable = [item for item in positions if item.get("can_sell")]
        if sellable and rng.random() < 0.12:
            pos = rng.choice(sellable)
            actions.append({"type": "sell", "symbol": pos["symbol"], "fraction": rng.choice([0.25, 0.5, 1.0]), "reason": "random_smoke"})
        if market and rng.random() < 0.18:
            held = {str(item["symbol"]) for item in positions}
            buyable = [item for item in market if not item.get("is_buy_blocked") and str(item["symbol"]) not in held]
            if buyable:
                pick = rng.choice(buyable[: min(20, len(buyable))])
                actions.append({"type": "buy", "symbol": pick["symbol"], "cash_fraction": rng.choice([0.05, 0.10, 0.15]), "reason": "random_smoke"})
        if not actions:
            actions = [{"type": "hold"}]
        obs, reward, done, _ = env.step(actions)
        total_reward += float(reward)
        steps += 1
    return {
        "lab_version": LAB_VERSION,
        "mode": "rl_random_agent_smoke",
        "range": {"start_date": start_date, "end_date": end_date},
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
        },
        "summary": env.summary(),
        "total_reward": round(total_reward, 6),
        "steps": steps,
        "trades": env.trades,
        "actions": env.actions_log,
        "equity_curve": env.equity_curve,
        "rl_environment": {
            "episode_unit": "one historical date range, recommended one month",
            "initial_budget": budget,
            "action_space": ["hold", "buy(symbol,cash_amount|cash_fraction)", "sell(symbol,fraction)"],
            "rules": ["point_in_time_5m_observation", "A_share_T_plus_1", "limit_up_buy_block", "limit_down_sell_block", "fees_and_slippage", "cash_and_position_constraints"],
            "reward_priority": "terminal_equity_first; drawdown/turnover/invalid_action are penalties",
        },
    }


RL_POLICY_FEATURES = [
    "bias",
    "return_from_open_pct",
    "price_vs_vwap_pct",
    "l2_main_net_ratio",
    "l2_super_net_ratio",
    "oib_ratio",
    "cvd_ratio",
    "book_imbalance_ratio",
    "log_total_amount",
    "cash_ratio",
    "position_count_ratio",
]

RL_PPO_FEATURE_SETS = {
    "weak_l2": [
        "bias",
        "return_from_open_pct",
        "price_vs_vwap_pct",
        "l2_main_net_ratio",
        "l2_super_net_ratio",
        "log_total_amount",
        "cash_ratio",
        "position_count_ratio",
    ],
    "full_l2_order_book": RL_POLICY_FEATURES,
}


def _resolve_rl_ppo_feature_names(feature_set: str) -> List[str]:
    key = str(feature_set or "full_l2_order_book")
    if key not in RL_PPO_FEATURE_SETS:
        raise ValueError(f"unknown PPO feature_set: {feature_set}")
    return list(RL_PPO_FEATURE_SETS[key])


def _rl_market_features(
    item: Dict[str, Any],
    obs: Dict[str, Any],
    max_positions: int,
    feature_names: Optional[Sequence[str]] = None,
) -> List[float]:
    cash = _safe_float(obs.get("cash"))
    equity = max(_safe_float(obs.get("equity")), 1.0)
    values = {
        "bias": 1.0,
        "return_from_open_pct": _clip(_safe_float(item.get("return_from_open_pct")) / 10.0, -1.0, 1.0),
        "price_vs_vwap_pct": _clip(_safe_float(item.get("price_vs_vwap_pct")) / 5.0, -1.0, 1.0),
        "l2_main_net_ratio": _clip(_safe_float(item.get("l2_main_net_ratio")) * 20.0, -1.0, 1.0),
        "l2_super_net_ratio": _clip(_safe_float(item.get("l2_super_net_ratio")) * 25.0, -1.0, 1.0),
        "oib_ratio": _clip(_safe_float(item.get("oib_ratio")) * 20.0, -1.0, 1.0),
        "cvd_ratio": _clip(_safe_float(item.get("cvd_ratio")) * 20.0, -1.0, 1.0),
        "book_imbalance_ratio": _clip(_safe_float(item.get("book_imbalance_ratio")), -1.0, 1.0),
        "log_total_amount": _clip(math.log10(max(_safe_float(item.get("total_amount")), 1.0)) / 10.0, 0.0, 1.0),
        "cash_ratio": _clip(cash / equity, 0.0, 1.0),
        "position_count_ratio": _clip(len(obs.get("positions") or []) / max(float(max_positions), 1.0), 0.0, 1.0),
    }
    names = list(feature_names or RL_POLICY_FEATURES)
    return [float(values[name]) for name in names]


TREND_PORTFOLIO_FEATURES = [
    "bias",
    "return_1d_pct",
    "return_3d_pct",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
    "amount_anomaly_20d",
    "breakout_vs_prev20_high_pct",
    "max_drawdown_from_20d_high_pct",
    "price_position_20d",
    "price_position_60d",
    "l2_main_net_ratio",
    "l2_super_net_ratio",
    "main_net_5d_ratio",
    "main_net_10d_ratio",
    "active_buy_strength",
    "positive_l2_bar_ratio",
    "order_imbalance_ratio",
    "cvd_ratio",
    "support_pressure_spread",
    "position_weight",
    "unrealized_return_pct",
    "holding_days",
    "runup_giveback_pct",
    "cash_ratio",
]


def _trend_panel_with_extended_features(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    frames: List[pd.DataFrame] = []
    for _, group in panel.groupby("symbol", sort=False):
        g = group.sort_values("trade_date").copy()
        amount_5 = g["total_amount"].rolling(5, min_periods=1).sum()
        amount_10 = g["total_amount"].rolling(10, min_periods=1).sum()
        g["main_net_5d_ratio"] = (g["l2_main_net_amount"].rolling(5, min_periods=1).sum() / amount_5.replace(0, pd.NA)).fillna(0.0)
        g["main_net_10d_ratio"] = (g["l2_main_net_amount"].rolling(10, min_periods=1).sum() / amount_10.replace(0, pd.NA)).fillna(0.0)
        g["super_net_5d_ratio"] = (g["l2_super_net_amount"].rolling(5, min_periods=1).sum() / amount_5.replace(0, pd.NA)).fillna(0.0)
        g["active_buy_strength"] = g.get("active_buy_strength", g["l2_buy_ratio"] - g["l2_sell_ratio"])
        g["support_pressure_spread"] = g.get("support_pressure_spread", g.get("buy_support_ratio", 0.0) - g.get("sell_pressure_ratio", 0.0))
        frames.append(g)
    return pd.concat(frames, ignore_index=True).sort_values(["trade_date", "symbol"]).reset_index(drop=True)


def _trend_is_blocked_for_buy(row: pd.Series) -> bool:
    if str(row.get("risk_flag_type") or "normal") != "normal":
        return True
    if _safe_float(row.get("is_limit_up_close")) > 0:
        return True
    return False


def _trend_is_blocked_for_sell(row: pd.Series) -> bool:
    if _safe_float(row.get("is_limit_down_close")) > 0:
        return True
    return False


class TrendPortfolioRLEnv:
    """
    Daily portfolio-management environment for trend holding.

    The agent observes only the current and historical daily features, then its
    target weights are executed at the next trade day's open.
    """

    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        config: Optional[RLTradingEnvConfig] = None,
        costs: Optional[IntradayCostParams] = None,
    ) -> None:
        self.panel = _trend_panel_with_extended_features(panel).sort_values(["trade_date", "symbol"]).reset_index(drop=True)
        self.config = config or RLTradingEnvConfig(max_positions=8, max_position_pct=0.35, max_total_exposure_pct=1.0)
        self.costs = costs or IntradayCostParams()
        self.dates = [str(v) for v in sorted(self.panel["trade_date"].unique())]
        self.panel_by_date = {str(k): g for k, g in self.panel.groupby("trade_date", sort=False)}
        self.row_by_symbol_date = {(str(row["symbol"]), str(row["trade_date"])): row for _, row in self.panel.iterrows()}
        self.reset()

    def reset(self) -> Dict[str, Any]:
        self.index = 0
        self.cash = float(self.config.budget)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.actions_log: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.prev_equity = float(self.config.budget)
        self.peak_equity = float(self.config.budget)
        self.max_drawdown_pct = 0.0
        return self._observation()

    def step(self, target_weights: Dict[str, float] | Sequence[Tuple[str, float]] | None = None) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        if self.index >= len(self.dates):
            return self._observation(), 0.0, True, {"reason": "episode_already_done"}
        decision_date = self.dates[self.index]
        if self.index + 1 >= len(self.dates):
            equity = self._mark_equity(decision_date)
            self._append_equity(decision_date, decision_date, equity)
            self.index = len(self.dates)
            reward = self._reward(equity=equity, step_return=0.0, turnover_cash=0.0, invalid_count=0, done=True)
            return self._observation(), reward, True, {"decision_date": decision_date, "trade_date": decision_date, "equity": round(equity, 2), "reason": "no_next_day"}

        execution_date = self.dates[self.index + 1]
        targets = self._normalize_targets(target_weights)
        invalid_count = 0
        turnover_cash = 0.0
        for symbol, target_weight in self._sell_orders(decision_date, execution_date, targets):
            ok, cash_delta = self._sell_to_weight(symbol, execution_date, target_weight, decision_date)
            turnover_cash += abs(cash_delta)
            invalid_count += 0 if ok else 1
        for symbol, target_weight in self._buy_orders(decision_date, execution_date, targets):
            ok, cash_delta = self._buy_to_weight(symbol, execution_date, target_weight, decision_date)
            turnover_cash += abs(cash_delta)
            invalid_count += 0 if ok else 1

        equity = self._mark_equity(execution_date)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown_pct = ((equity / self.peak_equity) - 1.0) * 100.0 if self.peak_equity else 0.0
        self.max_drawdown_pct = min(self.max_drawdown_pct, drawdown_pct)
        step_return = (equity / self.prev_equity - 1.0) if self.prev_equity else 0.0
        self.prev_equity = equity
        self._append_equity(execution_date, decision_date, equity)
        self.index += 1
        done = self.index >= len(self.dates)
        reward = self._reward(
            equity=equity,
            step_return=step_return,
            turnover_cash=turnover_cash,
            invalid_count=invalid_count,
            done=done,
            date=execution_date,
        )
        return self._observation(), reward, done, {
            "decision_date": decision_date,
            "trade_date": execution_date,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "open_positions": len(self.positions),
            "invalid_actions": invalid_count,
            "turnover_cash": round(turnover_cash, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
        }

    def summary(self) -> Dict[str, Any]:
        final_equity = float(self.equity_curve[-1]["equity"]) if self.equity_curve else float(self.config.budget)
        closed_returns = pd.Series([float(trade.get("net_return_pct") or 0.0) for trade in self.trades])
        return {
            "initial_budget": round(float(self.config.budget), 2),
            "final_equity": round(final_equity, 2),
            "total_return_pct": round((final_equity / float(self.config.budget) - 1.0) * 100.0, 2) if self.config.budget else 0.0,
            "max_drawdown_pct": round(float(self.max_drawdown_pct), 2),
            "trade_count": int(len(self.trades)),
            "open_positions": int(len(self.positions)),
            "cash": round(float(self.cash), 2),
            "avg_closed_return_pct": round(float(closed_returns.mean()), 2) if not closed_returns.empty else 0.0,
            "win_rate_pct": round(float((closed_returns > 0).mean() * 100.0), 2) if not closed_returns.empty else 0.0,
        }

    def _normalize_targets(self, target_weights: Dict[str, float] | Sequence[Tuple[str, float]] | None) -> Dict[str, float]:
        raw_items = []
        if isinstance(target_weights, dict):
            raw_items = list(target_weights.items())
        elif target_weights:
            raw_items = list(target_weights)
        cleaned: Dict[str, float] = {}
        for symbol, weight in raw_items:
            symbol_text = str(symbol).lower()
            if not _is_mainboard_10cm_symbol(symbol_text):
                continue
            cleaned[symbol_text] = max(0.0, float(weight))
        if not cleaned:
            return {}
        ranked = sorted(cleaned.items(), key=lambda item: item[1], reverse=True)[: int(self.config.max_positions)]
        capped = {symbol: min(weight, float(self.config.max_position_pct)) for symbol, weight in ranked}
        total = sum(capped.values())
        if total > float(self.config.max_total_exposure_pct) and total > 0:
            scale = float(self.config.max_total_exposure_pct) / total
            capped = {symbol: weight * scale for symbol, weight in capped.items()}
        return capped

    def _observation(self) -> Dict[str, Any]:
        date = self.dates[self.index] if self.index < len(self.dates) else (self.dates[-1] if self.dates else None)
        rows = self.panel_by_date.get(date, pd.DataFrame()) if date else pd.DataFrame()
        equity = self._mark_equity(date) if date else float(self.config.budget)
        positions = []
        for symbol, pos in sorted(self.positions.items()):
            row = self.row_by_symbol_date.get((symbol, date)) if date else None
            mark_price = _safe_float(row.get("close")) if row is not None else _safe_float(pos.get("gross_entry_price"))
            entry = _safe_float(pos.get("gross_entry_price"))
            market_value = _safe_float(pos.get("shares")) * mark_price
            peak_price = max(_safe_float(pos.get("peak_price"), entry), mark_price)
            pos["peak_price"] = peak_price
            unrealized = ((mark_price / entry) - 1.0) * 100.0 if entry else 0.0
            runup = ((peak_price / entry) - 1.0) * 100.0 if entry else 0.0
            positions.append(
                {
                    "symbol": symbol,
                    "entry_date": str(pos.get("entry_date")),
                    "shares": _safe_float(pos.get("shares")),
                    "market_value": round(market_value, 2),
                    "weight": market_value / max(equity, 1.0),
                    "cost_cash": round(_safe_float(pos.get("cost_cash")), 2),
                    "unrealized_return_pct": round(unrealized, 4),
                    "max_runup_pct": round(runup, 4),
                    "runup_giveback_pct": round(unrealized - runup, 4),
                    "holding_days": max(0, int(self.index) - int(pos.get("entry_index", self.index)) + 1),
                    "can_sell": bool(row is not None and str(row.get("trade_date")) != str(pos.get("entry_date")) and not _trend_is_blocked_for_sell(row)),
                }
            )
        market_rows = []
        position_by_symbol = {item["symbol"]: item for item in positions}
        if rows is not None and not rows.empty:
            ranked = rows.sort_values(["total_amount", "return_5d_pct"], ascending=[False, False]).head(int(self.config.max_observation_symbols))
            held_rows = rows[rows["symbol"].isin(position_by_symbol.keys())]
            if not held_rows.empty:
                ranked = pd.concat([held_rows, ranked], ignore_index=True).drop_duplicates("symbol", keep="first").head(int(self.config.max_observation_symbols))
            for _, row in ranked.iterrows():
                symbol = str(row["symbol"])
                pos = position_by_symbol.get(symbol, {})
                market_rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": str(row["trade_date"]),
                        "close": _safe_float(row.get("close")),
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "total_amount": _safe_float(row.get("total_amount")),
                        "return_1d_pct": _safe_float(row.get("return_1d_pct")),
                        "return_3d_pct": _safe_float(row.get("return_3d_pct")),
                        "return_5d_pct": _safe_float(row.get("return_5d_pct")),
                        "return_10d_pct": _safe_float(row.get("return_10d_pct")),
                        "return_20d_pct": _safe_float(row.get("return_20d_pct")),
                        "amount_anomaly_20d": _safe_float(row.get("amount_anomaly_20d")),
                        "breakout_vs_prev20_high_pct": _safe_float(row.get("breakout_vs_prev20_high_pct")),
                        "max_drawdown_from_20d_high_pct": _safe_float(row.get("max_drawdown_from_20d_high_pct")),
                        "price_position_20d": _safe_float(row.get("price_position_20d")),
                        "price_position_60d": _safe_float(row.get("price_position_60d")),
                        "l2_main_net_ratio": _safe_float(row.get("l2_main_net_ratio")),
                        "l2_super_net_ratio": _safe_float(row.get("l2_super_net_ratio")),
                        "main_net_5d_ratio": _safe_float(row.get("main_net_5d_ratio")),
                        "main_net_10d_ratio": _safe_float(row.get("main_net_10d_ratio")),
                        "active_buy_strength": _safe_float(row.get("active_buy_strength")),
                        "positive_l2_bar_ratio": _safe_float(row.get("positive_l2_bar_ratio")),
                        "order_imbalance_ratio": _safe_float(row.get("order_imbalance_ratio")),
                        "cvd_ratio": _safe_float(row.get("cvd_ratio")),
                        "support_pressure_spread": _safe_float(row.get("support_pressure_spread")),
                        "is_buy_blocked": _trend_is_blocked_for_buy(row),
                        "is_sell_blocked": _trend_is_blocked_for_sell(row),
                        "position_weight": _safe_float(pos.get("weight")),
                        "unrealized_return_pct": _safe_float(pos.get("unrealized_return_pct")),
                        "holding_days": _safe_float(pos.get("holding_days")),
                        "runup_giveback_pct": _safe_float(pos.get("runup_giveback_pct")),
                    }
                )
        return {
            "trade_date": date,
            "step_index": self.index,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "positions": positions,
            "market": market_rows,
        }

    def _sell_orders(self, decision_date: str, execution_date: str, targets: Dict[str, float]) -> List[Tuple[str, float]]:
        equity = max(self._mark_equity(execution_date), 1.0)
        orders = []
        for symbol in sorted(self.positions.keys()):
            current_weight = self._position_market_value(symbol, execution_date) / equity
            target_weight = targets.get(symbol, 0.0)
            if current_weight - target_weight >= 0.03:
                orders.append((symbol, target_weight))
        return orders

    def _buy_orders(self, decision_date: str, execution_date: str, targets: Dict[str, float]) -> List[Tuple[str, float]]:
        equity = max(self._mark_equity(execution_date), 1.0)
        orders = []
        for symbol, target_weight in sorted(targets.items(), key=lambda item: item[1], reverse=True):
            current_weight = self._position_market_value(symbol, execution_date) / equity
            if target_weight - current_weight >= 0.03:
                orders.append((symbol, target_weight))
        return orders

    def _buy_to_weight(self, symbol: str, date: str, target_weight: float, decision_date: str) -> Tuple[bool, float]:
        row = self.row_by_symbol_date.get((symbol, date))
        if row is None or _trend_is_blocked_for_buy(row):
            self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "buy_rejected", "reason": "not_buyable"})
            return False, 0.0
        if symbol not in self.positions and len(self.positions) >= int(self.config.max_positions):
            self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "buy_rejected", "reason": "max_positions"})
            return False, 0.0
        equity = self._mark_equity(date)
        current_value = self._position_market_value(symbol, date)
        target_value = max(0.0, float(target_weight)) * equity
        cash_amount = min(max(0.0, target_value - current_value), self.cash)
        if cash_amount < float(self.config.min_order_cash):
            return True, 0.0
        gross_price = _safe_float(row.get("open"))
        if gross_price <= 0:
            return False, 0.0
        effective_price = _apply_buy_costs(gross_price, self.costs)
        shares = cash_amount / effective_price
        self.cash -= cash_amount
        pos = self.positions.get(symbol)
        if pos:
            old_shares = _safe_float(pos.get("shares"))
            old_cost = _safe_float(pos.get("cost_cash"))
            new_shares = old_shares + shares
            new_cost = old_cost + cash_amount
            pos["shares"] = new_shares
            pos["cost_cash"] = new_cost
            pos["gross_entry_price"] = new_cost / new_shares if new_shares else gross_price
            pos["last_add_date"] = date
            pos["peak_price"] = max(_safe_float(pos.get("peak_price")), gross_price)
        else:
            self.positions[symbol] = {
                "symbol": symbol,
                "entry_date": str(row["trade_date"]),
                "entry_index": int(self.index) + 1,
                "gross_entry_price": gross_price,
                "shares": shares,
                "cost_cash": cash_amount,
                "peak_price": gross_price,
            }
        self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "buy", "cash": round(cash_amount, 2), "target_weight": round(float(target_weight), 4)})
        return True, cash_amount

    def _sell_to_weight(self, symbol: str, date: str, target_weight: float, decision_date: str) -> Tuple[bool, float]:
        pos = self.positions.get(symbol)
        row = self.row_by_symbol_date.get((symbol, date))
        if pos is None or row is None:
            return False, 0.0
        if str(row.get("trade_date")) == str(pos.get("entry_date")):
            self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "sell_rejected", "reason": "t1_locked"})
            return False, 0.0
        if _trend_is_blocked_for_sell(row):
            self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "sell_rejected", "reason": "sell_blocked"})
            return False, 0.0
        equity = max(self._mark_equity(date), 1.0)
        current_value = self._position_market_value(symbol, date)
        target_value = max(0.0, float(target_weight)) * equity
        sell_value = max(0.0, current_value - target_value)
        if sell_value < float(self.config.min_order_cash):
            return True, 0.0
        gross_price = _safe_float(row.get("open"))
        if gross_price <= 0:
            return False, 0.0
        gross_position_value = _safe_float(pos.get("shares")) * gross_price
        fraction = _clip(sell_value / max(gross_position_value, 1.0), 0.0, 1.0)
        shares = _safe_float(pos.get("shares")) * fraction
        proceeds = shares * _apply_sell_costs(gross_price, self.costs)
        cost_basis = _safe_float(pos.get("cost_cash")) * fraction
        self.cash += proceeds
        holding_days = max(1, int(self.index) + 1 - int(pos.get("entry_index", self.index)))
        self.trades.append(
            {
                "symbol": symbol,
                "entry_date": str(pos.get("entry_date")),
                "exit_date": str(row.get("trade_date")),
                "gross_entry_price": round(_safe_float(pos.get("gross_entry_price")), 4),
                "gross_exit_price": round(gross_price, 4),
                "sold_fraction": round(fraction, 4),
                "cost_cash": round(cost_basis, 2),
                "realized_cash": round(proceeds, 2),
                "pnl_cash": round(proceeds - cost_basis, 2),
                "net_return_pct": round((proceeds / cost_basis - 1.0) * 100.0, 4) if cost_basis else 0.0,
                "holding_days": holding_days,
                "exit_reason": "trend_target_rebalance",
            }
        )
        remaining_shares = _safe_float(pos.get("shares")) - shares
        remaining_cost = _safe_float(pos.get("cost_cash")) - cost_basis
        if remaining_shares <= 1e-9 or remaining_cost <= float(self.config.min_order_cash):
            self.positions.pop(symbol, None)
        else:
            pos["shares"] = remaining_shares
            pos["cost_cash"] = remaining_cost
        self.actions_log.append({"decision_date": decision_date, "trade_date": date, "symbol": symbol, "action": "sell", "fraction": round(fraction, 4), "target_weight": round(float(target_weight), 4)})
        return True, proceeds

    def _position_market_value(self, symbol: str, date: str) -> float:
        pos = self.positions.get(symbol)
        if not pos:
            return 0.0
        row = self.row_by_symbol_date.get((symbol, date))
        mark_price = _safe_float(row.get("close")) if row is not None else _safe_float(pos.get("gross_entry_price"))
        return _safe_float(pos.get("shares")) * mark_price

    def _mark_equity(self, date: Optional[str]) -> float:
        equity = float(self.cash)
        if not date:
            return equity
        for symbol in self.positions:
            equity += self._position_market_value(symbol, date)
        return equity

    def _append_equity(self, date: str, decision_date: str, equity: float) -> None:
        drawdown_pct = ((equity / self.peak_equity) - 1.0) * 100.0 if self.peak_equity else 0.0
        self.equity_curve.append(
            {
                "trade_date": date,
                "decision_date": decision_date,
                "cash": round(self.cash, 2),
                "equity": round(equity, 2),
                "open_positions": len(self.positions),
                "drawdown_pct": round(drawdown_pct, 4),
            }
        )

    def _reward(self, *, equity: float, step_return: float, turnover_cash: float, invalid_count: int, done: bool, date: Optional[str] = None) -> float:
        reward_cfg = self.config.reward
        reward = float(reward_cfg.step_return_weight) * float(step_return)
        reward -= float(reward_cfg.turnover_penalty_weight) * (float(turnover_cash) / max(float(self.config.budget), 1.0)) * 0.4
        reward -= float(reward_cfg.invalid_action_penalty) * float(invalid_count)
        if date:
            hold_bonus = 0.0
            for symbol, pos in self.positions.items():
                row = self.row_by_symbol_date.get((symbol, date))
                if row is None:
                    continue
                entry = _safe_float(pos.get("gross_entry_price"))
                if entry <= 0:
                    continue
                mark_price = _safe_float(row.get("close"))
                unrealized = (mark_price / entry) - 1.0
                holding_days = max(1, int(self.index) + 1 - int(pos.get("entry_index", self.index)))
                hold_bonus += max(0.0, unrealized) * min(holding_days, 10) / 10.0
            reward += float(reward_cfg.hold_winner_reward_weight) * float(hold_bonus)
        if done:
            terminal_return = (float(equity) / float(self.config.budget) - 1.0) if self.config.budget else 0.0
            drawdown_penalty = abs(float(self.max_drawdown_pct)) / 100.0
            reward += float(reward_cfg.terminal_return_weight) * terminal_return * 5.0
            reward -= float(reward_cfg.max_drawdown_penalty_weight) * drawdown_penalty
        return float(reward)


def _trend_feature_vector(item: Dict[str, Any], obs: Dict[str, Any], max_holding_days: int = 30) -> List[float]:
    cash = _safe_float(obs.get("cash"))
    equity = max(_safe_float(obs.get("equity")), 1.0)
    values = {
        "bias": 1.0,
        "return_1d_pct": _clip(_safe_float(item.get("return_1d_pct")) / 10.0, -1.0, 1.0),
        "return_3d_pct": _clip(_safe_float(item.get("return_3d_pct")) / 18.0, -1.0, 1.0),
        "return_5d_pct": _clip(_safe_float(item.get("return_5d_pct")) / 28.0, -1.0, 1.0),
        "return_10d_pct": _clip(_safe_float(item.get("return_10d_pct")) / 45.0, -1.0, 1.0),
        "return_20d_pct": _clip(_safe_float(item.get("return_20d_pct")) / 80.0, -1.0, 1.0),
        "amount_anomaly_20d": _clip((_safe_float(item.get("amount_anomaly_20d")) - 1.0) / 3.0, -1.0, 1.0),
        "breakout_vs_prev20_high_pct": _clip(_safe_float(item.get("breakout_vs_prev20_high_pct")) / 12.0, -1.0, 1.0),
        "max_drawdown_from_20d_high_pct": _clip(_safe_float(item.get("max_drawdown_from_20d_high_pct")) / 30.0, -1.0, 0.0),
        "price_position_20d": _clip(_safe_float(item.get("price_position_20d")), 0.0, 1.0),
        "price_position_60d": _clip(_safe_float(item.get("price_position_60d")), 0.0, 1.0),
        "l2_main_net_ratio": _clip(_safe_float(item.get("l2_main_net_ratio")) * 20.0, -1.0, 1.0),
        "l2_super_net_ratio": _clip(_safe_float(item.get("l2_super_net_ratio")) * 25.0, -1.0, 1.0),
        "main_net_5d_ratio": _clip(_safe_float(item.get("main_net_5d_ratio")) * 20.0, -1.0, 1.0),
        "main_net_10d_ratio": _clip(_safe_float(item.get("main_net_10d_ratio")) * 20.0, -1.0, 1.0),
        "active_buy_strength": _clip(_safe_float(item.get("active_buy_strength")) / 10.0, -1.0, 1.0),
        "positive_l2_bar_ratio": _clip(_safe_float(item.get("positive_l2_bar_ratio")), 0.0, 1.0),
        "order_imbalance_ratio": _clip(_safe_float(item.get("order_imbalance_ratio")) * 20.0, -1.0, 1.0),
        "cvd_ratio": _clip(_safe_float(item.get("cvd_ratio")) * 20.0, -1.0, 1.0),
        "support_pressure_spread": _clip(_safe_float(item.get("support_pressure_spread")) * 10.0, -1.0, 1.0),
        "position_weight": _clip(_safe_float(item.get("position_weight")), 0.0, 1.0),
        "unrealized_return_pct": _clip(_safe_float(item.get("unrealized_return_pct")) / 40.0, -1.0, 1.0),
        "holding_days": _clip(_safe_float(item.get("holding_days")) / max(float(max_holding_days), 1.0), 0.0, 1.0),
        "runup_giveback_pct": _clip(_safe_float(item.get("runup_giveback_pct")) / 30.0, -1.0, 0.0),
        "cash_ratio": _clip(cash / equity, 0.0, 1.0),
    }
    return [float(values[name]) for name in TREND_PORTFOLIO_FEATURES]


class TrendPortfolioPPOGym(gym.Env if gym is not None else object):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        env_config: Optional[RLTradingEnvConfig] = None,
        top_n: int = 30,
        episode_min_days: int = 10,
        episode_max_days: int = 30,
        random_episode: bool = True,
    ) -> None:
        if gym is None or spaces is None:
            raise RuntimeError("gymnasium is required for TrendPortfolioPPOGym")
        if gym is not None:
            super().__init__()
        self.full_panel = panel.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
        self.env_config = env_config or RLTradingEnvConfig()
        self.top_n = int(top_n)
        self.episode_min_days = max(2, int(episode_min_days))
        self.episode_max_days = max(self.episode_min_days, int(episode_max_days))
        self.random_episode = bool(random_episode)
        self.trade_dates = [str(v) for v in sorted(self.full_panel["trade_date"].unique())]
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.top_n + 1,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(self.top_n * len(TREND_PORTFOLIO_FEATURES) + 5,),
            dtype=np.float32,
        )
        self.env: Optional[TrendPortfolioRLEnv] = None
        self.last_obs_dict: Dict[str, Any] = {}

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        if gym is not None:
            super().reset(seed=seed)
        panel = self._sample_episode_panel()
        self.env = TrendPortfolioRLEnv(panel, config=self.env_config)
        self.last_obs_dict = self.env.reset()
        return self._flatten_obs(self.last_obs_dict), {"trade_date": self.last_obs_dict.get("trade_date")}

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        if self.env is None:
            panel = self._sample_episode_panel()
            self.env = TrendPortfolioRLEnv(panel, config=self.env_config)
            self.last_obs_dict = self.env.reset()
        targets = self._action_to_targets(np.asarray(action, dtype=float), self.last_obs_dict)
        obs, reward, done, info = self.env.step(targets)
        self.last_obs_dict = obs
        return self._flatten_obs(obs), float(reward), bool(done), False, info

    def _sample_episode_panel(self) -> pd.DataFrame:
        dates = self.trade_dates
        if not dates:
            return self.full_panel.copy()
        if (not self.random_episode) or len(dates) <= self.episode_max_days:
            selected = dates
        else:
            rng = self.np_random if hasattr(self, "np_random") else np.random.default_rng()
            length = int(rng.integers(self.episode_min_days, self.episode_max_days + 1))
            length = min(length, len(dates))
            start = int(rng.integers(0, len(dates) - length + 1))
            selected = dates[start : start + length]
        return self.full_panel[self.full_panel["trade_date"].isin(selected)].copy()

    def _flatten_obs(self, obs: Dict[str, Any]) -> np.ndarray:
        rows = list(obs.get("market") or [])[: self.top_n]
        values: List[float] = []
        for idx in range(self.top_n):
            if idx < len(rows):
                values.extend(_trend_feature_vector(rows[idx], obs))
            else:
                values.extend([0.0] * len(TREND_PORTFOLIO_FEATURES))
        equity = max(_safe_float(obs.get("equity")), 1.0)
        cash = _safe_float(obs.get("cash"))
        positions = obs.get("positions") or []
        values.extend(
            [
                _clip(cash / equity, 0.0, 1.0),
                _clip(len(positions) / max(float(self.env_config.max_positions), 1.0), 0.0, 1.0),
                _clip((equity / max(float(self.env_config.budget), 1.0)) - 1.0, -1.0, 1.0),
                _clip(_safe_float(obs.get("step_index")) / max(float(self.episode_max_days), 1.0), 0.0, 1.0),
                _clip(sum(_safe_float(item.get("market_value")) for item in positions) / equity, 0.0, 1.0),
            ]
        )
        return np.asarray(values, dtype=np.float32)

    def _action_to_targets(self, action: np.ndarray, obs: Dict[str, Any]) -> Dict[str, float]:
        market = list(obs.get("market") or [])[: self.top_n]
        if not market:
            return {}
        action = np.nan_to_num(action, nan=0.0, posinf=1.0, neginf=0.0)
        logits = np.clip(action[: len(market) + 1], 0.0, 1.0) * 4.0
        if logits.size <= 1:
            return {}
        logits = logits - float(np.max(logits))
        probs = np.exp(logits)
        probs = probs / max(float(probs.sum()), 1e-9)
        stock_probs = probs[:-1]
        cash_prob = float(probs[-1])
        active_mass = float(stock_probs.sum())
        if active_mass <= 1e-9:
            return {}
        desired_exposure = float(self.env_config.max_total_exposure_pct) * (1.0 - cash_prob)
        if desired_exposure <= 0.02:
            return {}
        raw = stock_probs / active_mass * desired_exposure
        raw = np.minimum(raw, float(self.env_config.max_position_pct))
        if float(raw.sum()) > float(self.env_config.max_total_exposure_pct):
            raw = raw / float(raw.sum()) * float(self.env_config.max_total_exposure_pct)
        targets = {str(item["symbol"]): float(weight) for item, weight in zip(market, raw) if float(weight) >= 0.01}
        return targets

    def render(self) -> None:
        return None


def _dot(weights: Sequence[float], features: Sequence[float]) -> float:
    return sum(float(w) * float(v) for w, v in zip(weights, features))


def _policy_actions_from_weights(obs: Dict[str, Any], weights: Sequence[float], config: RLTradingEnvConfig) -> List[Dict[str, Any]]:
    buy_weights = weights[: len(RL_POLICY_FEATURES)]
    sell_weights = weights[len(RL_POLICY_FEATURES) : len(RL_POLICY_FEATURES) * 2]
    control = list(weights[len(RL_POLICY_FEATURES) * 2 :])
    buy_threshold = 0.35 + 0.35 * math.tanh(control[0] if len(control) > 0 else 0.0)
    sell_threshold = 0.25 + 0.35 * math.tanh(control[1] if len(control) > 1 else 0.0)
    buy_fraction = _clip(0.04 + 0.16 * (1.0 + math.tanh(control[2] if len(control) > 2 else 0.0)) / 2.0, 0.03, 0.22)
    sell_fraction = _clip(0.25 + 0.75 * (1.0 + math.tanh(control[3] if len(control) > 3 else 0.0)) / 2.0, 0.2, 1.0)
    max_buys = int(round(_clip(1 + 3 * (1.0 + math.tanh(control[4] if len(control) > 4 else 0.0)) / 2.0, 1.0, 4.0)))
    max_sells = int(round(_clip(1 + 3 * (1.0 + math.tanh(control[5] if len(control) > 5 else 0.0)) / 2.0, 1.0, 4.0)))

    actions: List[Dict[str, Any]] = []
    position_symbols = {str(pos["symbol"]) for pos in (obs.get("positions") or [])}
    sell_candidates = []
    market_by_symbol = {str(item["symbol"]): item for item in (obs.get("market") or [])}
    for pos in obs.get("positions") or []:
        if not pos.get("can_sell"):
            continue
        item = market_by_symbol.get(str(pos["symbol"]), {})
        features = _rl_market_features({**item, **pos}, obs, int(config.max_positions))
        score = _dot(sell_weights, features)
        if score >= sell_threshold:
            sell_candidates.append((score, str(pos["symbol"])))
    for _, symbol in sorted(sell_candidates, reverse=True)[:max_sells]:
        actions.append({"type": "sell", "symbol": symbol, "fraction": sell_fraction, "reason": "learned_policy"})

    buy_candidates = []
    for item in obs.get("market") or []:
        symbol = str(item["symbol"])
        if symbol in position_symbols or item.get("is_buy_blocked"):
            continue
        features = _rl_market_features(item, obs, int(config.max_positions))
        score = _dot(buy_weights, features)
        if score >= buy_threshold:
            buy_candidates.append((score, symbol))
    for _, symbol in sorted(buy_candidates, reverse=True)[:max_buys]:
        actions.append({"type": "buy", "symbol": symbol, "cash_fraction": buy_fraction, "reason": "learned_policy"})

    return actions or [{"type": "hold"}]


def _run_rl_episode(panel: pd.DataFrame, weights: Sequence[float], env_config: RLTradingEnvConfig) -> Dict[str, Any]:
    env = RLTradingEnv(panel, config=env_config)
    obs = env.reset()
    done = False
    total_reward = 0.0
    while not done:
        actions = _policy_actions_from_weights(obs, weights, env_config)
        obs, reward, done, _ = env.step(actions)
        total_reward += float(reward)
    summary = env.summary()
    score = (
        float(summary["total_return_pct"])
        - abs(float(summary["max_drawdown_pct"])) * 0.18
        - max(0, int(summary["trade_count"]) - 80) * 0.01
    )
    return {
        "score": round(float(score), 6),
        "total_reward": round(float(total_reward), 6),
        "summary": summary,
        "trades": env.trades,
        "actions": env.actions_log,
        "equity_curve": env.equity_curve,
    }


def _target_policy_weight_count(hidden_size: int) -> int:
    feature_count = len(RL_POLICY_FEATURES)
    return feature_count * hidden_size + hidden_size + hidden_size + 4


def _unpack_target_policy(weights: Sequence[float], hidden_size: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    feature_count = len(RL_POLICY_FEATURES)
    raw = np.asarray(list(weights), dtype=float)
    expected = _target_policy_weight_count(hidden_size)
    if raw.size < expected:
        raw = np.pad(raw, (0, expected - raw.size))
    offset = 0
    w1 = raw[offset : offset + feature_count * hidden_size].reshape(feature_count, hidden_size)
    offset += feature_count * hidden_size
    b1 = raw[offset : offset + hidden_size]
    offset += hidden_size
    w2 = raw[offset : offset + hidden_size]
    offset += hidden_size
    controls = raw[offset : offset + 4]
    return w1, b1, w2, controls


def _target_policy_actions_from_weights(obs: Dict[str, Any], weights: Sequence[float], config: RLTradingEnvConfig, hidden_size: int) -> List[Dict[str, Any]]:
    w1, b1, w2, controls = _unpack_target_policy(weights, hidden_size)
    max_names = max(1, int(round(2 + 6 * (1.0 + math.tanh(float(controls[0]))) / 2.0)))
    max_total_exposure = _clip(0.35 + 0.65 * (1.0 + math.tanh(float(controls[1]))) / 2.0, 0.20, 1.0)
    max_single_weight = _clip(0.08 + 0.22 * (1.0 + math.tanh(float(controls[2]))) / 2.0, 0.05, 0.35)
    rebalance_threshold = _clip(0.015 + 0.08 * (1.0 + math.tanh(float(controls[3]))) / 2.0, 0.01, 0.12)
    market = obs.get("market") or []
    positions = {str(item["symbol"]): item for item in (obs.get("positions") or [])}
    equity = max(_safe_float(obs.get("equity")), 1.0)

    scored = []
    for item in market:
        if item.get("is_buy_blocked") and str(item["symbol"]) not in positions:
            continue
        features = np.asarray(_rl_market_features(item, obs, int(config.max_positions)), dtype=float)
        hidden = np.tanh(features @ w1 + b1)
        score = float(hidden @ w2)
        scored.append((score, str(item["symbol"])))
    scored.sort(reverse=True)

    selected = [symbol for _, symbol in scored[:max_names]]
    if not selected:
        selected = list(positions.keys())[:max_names]
    positive = np.asarray([max(score, 0.0) for score, symbol in scored[:max_names]], dtype=float)
    if positive.size == 0 or float(positive.sum()) <= 0:
        weights_target = np.asarray([1.0 / len(selected) for _ in selected], dtype=float) if selected else np.asarray([], dtype=float)
    else:
        weights_target = positive / positive.sum()
    weights_target = weights_target * max_total_exposure
    weights_target = np.minimum(weights_target, max_single_weight)
    if weights_target.sum() > max_total_exposure:
        weights_target = weights_target / weights_target.sum() * max_total_exposure
    target_by_symbol = {symbol: float(weight) for symbol, weight in zip(selected, weights_target)}

    actions: List[Dict[str, Any]] = []
    for symbol, pos in positions.items():
        current_weight = _safe_float(pos.get("market_value")) / equity
        target_weight = target_by_symbol.get(symbol, 0.0)
        if current_weight <= 0:
            continue
        if current_weight - target_weight >= rebalance_threshold and pos.get("can_sell"):
            fraction = _clip((current_weight - target_weight) / current_weight, 0.0, 1.0)
            actions.append({"type": "sell", "symbol": symbol, "fraction": fraction, "reason": "target_policy_rebalance"})

    held_symbols = set(positions.keys())
    for symbol, target_weight in target_by_symbol.items():
        current_value = _safe_float(positions.get(symbol, {}).get("market_value")) if symbol in positions else 0.0
        current_weight = current_value / equity
        if target_weight - current_weight >= rebalance_threshold:
            cash_amount = (target_weight - current_weight) * equity
            actions.append({"type": "buy", "symbol": symbol, "cash_amount": cash_amount, "reason": "target_policy_rebalance"})
        held_symbols.add(symbol)
    return actions or [{"type": "hold"}]


def _run_rl_target_episode(panel: pd.DataFrame, weights: Sequence[float], env_config: RLTradingEnvConfig, hidden_size: int) -> Dict[str, Any]:
    env = RLTradingEnv(panel, config=env_config)
    obs = env.reset()
    done = False
    total_reward = 0.0
    while not done:
        actions = _target_policy_actions_from_weights(obs, weights, env_config, hidden_size)
        obs, reward, done, _ = env.step(actions)
        total_reward += float(reward)
    summary = env.summary()
    score = (
        float(summary["total_return_pct"]) * 1.0
        - abs(float(summary["max_drawdown_pct"])) * 0.16
        - max(0, int(summary["trade_count"]) - 120) * 0.006
    )
    return {
        "score": round(float(score), 6),
        "total_reward": round(float(total_reward), 6),
        "summary": summary,
        "trades": env.trades,
        "actions": env.actions_log,
        "equity_curve": env.equity_curve,
    }


class ASharePPOTradingGym(gym.Env if gym is not None else object):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        env_config: Optional[RLTradingEnvConfig] = None,
        top_n: int = 20,
        feature_set: str = "full_l2_order_book",
    ) -> None:
        if gym is None or spaces is None:
            raise RuntimeError("gymnasium is required for ASharePPOTradingGym")

        if gym is not None:
            super().__init__()
        self.panel = panel
        self.env_config = env_config or RLTradingEnvConfig()
        self.top_n = int(top_n)
        self.feature_set = str(feature_set or "full_l2_order_book")
        self.feature_names = _resolve_rl_ppo_feature_names(self.feature_set)
        self.feature_count = len(self.feature_names)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.top_n,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(self.top_n * self.feature_count + 4,),
            dtype=np.float32,
        )
        self.env: Optional[RLTradingEnv] = None
        self.last_obs_dict: Dict[str, Any] = {}

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        if gym is not None:
            super().reset(seed=seed)
        self.env = RLTradingEnv(self.panel, config=self.env_config)
        self.last_obs_dict = self.env.reset()
        return self._flatten_obs(self.last_obs_dict), {"bucket_start": self.last_obs_dict.get("bucket_start")}

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        if self.env is None:
            self.env = RLTradingEnv(self.panel, config=self.env_config)
            self.last_obs_dict = self.env.reset()
        actions = self._action_to_orders(np.asarray(action, dtype=float), self.last_obs_dict)
        obs, reward, done, info = self.env.step(actions)
        self.last_obs_dict = obs
        return self._flatten_obs(obs), float(reward), bool(done), False, info

    def _flatten_obs(self, obs: Dict[str, Any]) -> np.ndarray:
        rows = list(obs.get("market") or [])[: self.top_n]
        values: List[float] = []
        for idx in range(self.top_n):
            if idx < len(rows):
                values.extend(_rl_market_features(rows[idx], obs, int(self.env_config.max_positions), self.feature_names))
            else:
                values.extend([0.0] * self.feature_count)
        equity = max(_safe_float(obs.get("equity")), 1.0)
        cash = _safe_float(obs.get("cash"))
        positions = obs.get("positions") or []
        values.extend(
            [
                _clip(cash / equity, 0.0, 1.0),
                _clip(len(positions) / max(float(self.env_config.max_positions), 1.0), 0.0, 1.0),
                _clip((equity / max(float(self.env_config.budget), 1.0)) - 1.0, -1.0, 1.0),
                _clip(_safe_float(obs.get("step_index")) / 4096.0, 0.0, 1.0),
            ]
        )
        return np.asarray(values, dtype=np.float32)

    def _action_to_orders(self, action: np.ndarray, obs: Dict[str, Any]) -> List[Dict[str, Any]]:
        market = list(obs.get("market") or [])[: self.top_n]
        if not market:
            return [{"type": "hold"}]
        action = np.nan_to_num(action, nan=0.0, posinf=1.0, neginf=0.0)
        action = np.clip(action[: len(market)], 0.0, 1.0)
        if float(action.sum()) <= 1e-9:
            return [{"type": "hold"}]
        exposure = 0.25 + 0.75 * min(float(action.sum()) / max(float(len(market)), 1.0), 1.0)
        raw_weights = action / float(action.sum()) * exposure
        raw_weights = np.minimum(raw_weights, float(self.env_config.max_position_pct))
        if float(raw_weights.sum()) > float(self.env_config.max_total_exposure_pct):
            raw_weights = raw_weights / float(raw_weights.sum()) * float(self.env_config.max_total_exposure_pct)
        equity = max(_safe_float(obs.get("equity")), 1.0)
        positions = {str(item["symbol"]): item for item in (obs.get("positions") or [])}
        target = {str(item["symbol"]): float(weight) for item, weight in zip(market, raw_weights)}
        actions: List[Dict[str, Any]] = []
        rebalance_threshold = 0.025
        for symbol, pos in positions.items():
            current_weight = _safe_float(pos.get("market_value")) / equity
            target_weight = target.get(symbol, 0.0)
            if current_weight - target_weight >= rebalance_threshold and pos.get("can_sell"):
                actions.append(
                    {
                        "type": "sell",
                        "symbol": symbol,
                        "fraction": _clip((current_weight - target_weight) / current_weight, 0.0, 1.0),
                        "reason": "ppo_target_rebalance",
                    }
                )
        for item in market:
            symbol = str(item["symbol"])
            if item.get("is_buy_blocked"):
                continue
            current_weight = _safe_float(positions.get(symbol, {}).get("market_value")) / equity if symbol in positions else 0.0
            target_weight = target.get(symbol, 0.0)
            if target_weight - current_weight >= rebalance_threshold:
                actions.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "cash_amount": (target_weight - current_weight) * equity,
                        "reason": "ppo_target_rebalance",
                    }
                )
        return actions or [{"type": "hold"}]

    def render(self) -> None:
        return None


def train_rl_ppo_policy(
    config: RLPPOTrainerConfig,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    model_out: Optional[str | Path] = None,
) -> Dict[str, Any]:
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.utils import set_random_seed

    set_random_seed(int(config.seed))
    panel = load_intraday_panel(
        config.start_date,
        config.end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(config.max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(config.budget),
        max_positions=8,
        max_position_pct=0.35,
        max_total_exposure_pct=1.0,
        max_observation_symbols=int(config.max_observation_symbols),
    )
    gym_env = Monitor(
        ASharePPOTradingGym(
            panel,
            env_config=env_config,
            top_n=int(config.max_observation_symbols),
            feature_set=config.feature_set,
        )
    )
    policy_kwargs = {"net_arch": {"pi": [128, 64], "vf": [128, 64]}}
    model = PPO(
        "MlpPolicy",
        gym_env,
        learning_rate=float(config.learning_rate),
        n_steps=int(config.n_steps),
        batch_size=int(config.batch_size),
        n_epochs=int(config.n_epochs),
        gamma=float(config.gamma),
        seed=int(config.seed),
        policy_kwargs=policy_kwargs,
        verbose=0,
    )
    model.learn(total_timesteps=int(config.total_timesteps), progress_bar=False)
    if model_out:
        Path(model_out).parent.mkdir(parents=True, exist_ok=True)
        model.save(str(model_out))

    eval_env = ASharePPOTradingGym(
        panel,
        env_config=env_config,
        top_n=int(config.max_observation_symbols),
        feature_set=config.feature_set,
    )
    obs, _ = eval_env.reset(seed=int(config.seed) + 1000)
    done = False
    total_reward = 0.0
    steps = 0
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = eval_env.step(action)
        done = bool(terminated or truncated)
        total_reward += float(reward)
        steps += 1
    env = eval_env.env
    summary = env.summary() if env else {}
    return {
        "lab_version": LAB_VERSION,
        "mode": "rl_ppo_target_policy",
        "config": asdict(config),
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "model_path": str(model_out) if model_out else None,
        "summary": summary,
        "total_reward": round(total_reward, 6),
        "steps": steps,
        "target_met": bool(float(summary.get("total_return_pct") or 0.0) >= float(config.target_return_pct)),
        "trades": env.trades if env else [],
        "actions": env.actions_log if env else [],
        "equity_curve": env.equity_curve if env else [],
        "policy_note": "Stable-Baselines3 PPO MlpPolicy over fixed top-N point-in-time 5m observations; continuous actions map to target portfolio weights.",
        "feature_names": _resolve_rl_ppo_feature_names(config.feature_set),
    }


def eval_rl_ppo_policy(
    *,
    model_path: str | Path,
    start_date: str,
    end_date: str,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    budget: float = 1_000_000.0,
    max_symbols_per_day: int = 40,
    max_observation_symbols: int = 20,
    seed: int = 101,
    feature_set: str = "full_l2_order_book",
) -> Dict[str, Any]:
    from stable_baselines3 import PPO

    panel = load_intraday_panel(
        start_date,
        end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(budget),
        max_positions=8,
        max_position_pct=0.35,
        max_total_exposure_pct=1.0,
        max_observation_symbols=int(max_observation_symbols),
    )
    eval_env = ASharePPOTradingGym(
        panel,
        env_config=env_config,
        top_n=int(max_observation_symbols),
        feature_set=feature_set,
    )
    model = PPO.load(str(model_path), env=None)
    obs, _ = eval_env.reset(seed=int(seed))
    done = False
    total_reward = 0.0
    steps = 0
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = eval_env.step(action)
        done = bool(terminated or truncated)
        total_reward += float(reward)
        steps += 1
    env = eval_env.env
    summary = env.summary() if env else {}
    return {
        "lab_version": LAB_VERSION,
        "mode": "rl_ppo_target_policy_eval",
        "model_path": str(model_path),
        "range": {"start_date": start_date, "end_date": end_date},
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "summary": summary,
        "total_reward": round(total_reward, 6),
        "steps": steps,
        "trades": env.trades if env else [],
        "actions": env.actions_log if env else [],
        "equity_curve": env.equity_curve if env else [],
        "policy_note": "Out-of-sample PPO evaluation only; no training or parameter update.",
        "feature_names": _resolve_rl_ppo_feature_names(feature_set),
    }


def train_trend_portfolio_ppo_policy(
    config: TrendPortfolioPPOTrainerConfig,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    model_out: Optional[str | Path] = None,
) -> Dict[str, Any]:
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.utils import set_random_seed

    set_random_seed(int(config.seed))
    panel = load_trend_daily_panel(
        config.start_date,
        config.end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(config.max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(config.budget),
        max_positions=8,
        max_position_pct=0.35,
        max_total_exposure_pct=1.0,
        min_order_cash=5_000.0,
        max_observation_symbols=int(config.max_observation_symbols),
        reward=RLRewardConfig(
            terminal_return_weight=1.0,
            max_drawdown_penalty_weight=0.12,
            step_return_weight=0.04,
            turnover_penalty_weight=0.006,
            invalid_action_penalty=0.02,
            idle_cash_penalty_weight=0.0,
            hold_winner_reward_weight=0.01,
        ),
    )
    gym_env = Monitor(
        TrendPortfolioPPOGym(
            panel,
            env_config=env_config,
            top_n=int(config.max_observation_symbols),
            episode_min_days=int(config.episode_min_days),
            episode_max_days=int(config.episode_max_days),
            random_episode=True,
        )
    )
    policy_kwargs = {"net_arch": {"pi": [256, 128], "vf": [256, 128]}}
    model = PPO(
        "MlpPolicy",
        gym_env,
        learning_rate=float(config.learning_rate),
        n_steps=int(config.n_steps),
        batch_size=int(config.batch_size),
        n_epochs=int(config.n_epochs),
        gamma=float(config.gamma),
        ent_coef=float(config.ent_coef),
        clip_range=float(config.clip_range),
        seed=int(config.seed),
        policy_kwargs=policy_kwargs,
        verbose=0,
    )
    model.learn(total_timesteps=int(config.total_timesteps), progress_bar=False)
    if model_out:
        Path(model_out).parent.mkdir(parents=True, exist_ok=True)
        model.save(str(model_out))

    eval_env = TrendPortfolioPPOGym(
        panel,
        env_config=env_config,
        top_n=int(config.max_observation_symbols),
        episode_min_days=int(config.episode_min_days),
        episode_max_days=int(config.episode_max_days),
        random_episode=False,
    )
    obs, _ = eval_env.reset(seed=int(config.seed) + 1000)
    done = False
    total_reward = 0.0
    steps = 0
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = eval_env.step(action)
        done = bool(terminated or truncated)
        total_reward += float(reward)
        steps += 1
    env = eval_env.env
    summary = env.summary() if env else {}
    return {
        "lab_version": LAB_VERSION,
        "mode": "trend_portfolio_ppo_policy",
        "config": asdict(config),
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "model_path": str(model_out) if model_out else None,
        "summary": summary,
        "total_reward": round(total_reward, 6),
        "steps": steps,
        "target_met": bool(float(summary.get("total_return_pct") or 0.0) >= float(config.target_return_pct)),
        "trades": env.trades if env else [],
        "actions": env.actions_log if env else [],
        "equity_curve": env.equity_curve if env else [],
        "policy_note": "TrendPortfolioPPOGym: daily target-weight portfolio RL, next-day open execution, T+1 and limit rules enforced by environment.",
        "feature_names": TREND_PORTFOLIO_FEATURES,
    }


def eval_trend_portfolio_ppo_policy(
    *,
    model_path: str | Path,
    start_date: str,
    end_date: str,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    budget: float = 1_000_000.0,
    max_symbols_per_day: int = 80,
    max_observation_symbols: int = 30,
    episode_min_days: int = 10,
    episode_max_days: int = 30,
    seed: int = 101,
) -> Dict[str, Any]:
    from stable_baselines3 import PPO

    panel = load_trend_daily_panel(
        start_date,
        end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(budget),
        max_positions=8,
        max_position_pct=0.35,
        max_total_exposure_pct=1.0,
        min_order_cash=5_000.0,
        max_observation_symbols=int(max_observation_symbols),
        reward=RLRewardConfig(
            terminal_return_weight=1.0,
            max_drawdown_penalty_weight=0.12,
            step_return_weight=0.04,
            turnover_penalty_weight=0.006,
            invalid_action_penalty=0.02,
            idle_cash_penalty_weight=0.0,
            hold_winner_reward_weight=0.01,
        ),
    )
    eval_env = TrendPortfolioPPOGym(
        panel,
        env_config=env_config,
        top_n=int(max_observation_symbols),
        episode_min_days=int(episode_min_days),
        episode_max_days=int(episode_max_days),
        random_episode=False,
    )
    model = PPO.load(str(model_path), env=None)
    obs, _ = eval_env.reset(seed=int(seed))
    done = False
    total_reward = 0.0
    steps = 0
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = eval_env.step(action)
        done = bool(terminated or truncated)
        total_reward += float(reward)
        steps += 1
    env = eval_env.env
    summary = env.summary() if env else {}
    return {
        "lab_version": LAB_VERSION,
        "mode": "trend_portfolio_ppo_policy_eval",
        "model_path": str(model_path),
        "range": {"start_date": start_date, "end_date": end_date},
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "summary": summary,
        "total_reward": round(total_reward, 6),
        "steps": steps,
        "trades": env.trades if env else [],
        "actions": env.actions_log if env else [],
        "equity_curve": env.equity_curve if env else [],
        "policy_note": "Out-of-sample trend portfolio PPO evaluation only; no training or parameter update.",
        "feature_names": TREND_PORTFOLIO_FEATURES,
    }


def train_rl_target_policy_search(
    config: RLTargetPolicyTrainerConfig,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    panel = load_intraday_panel(
        config.start_date,
        config.end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(config.max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(config.budget),
        max_positions=8,
        max_position_pct=0.35,
        max_total_exposure_pct=1.0,
        max_observation_symbols=int(config.max_observation_symbols),
    )
    rng = random.Random(int(config.seed))
    weight_count = _target_policy_weight_count(int(config.hidden_size))
    center = [0.0 for _ in range(weight_count)]
    sigma = float(config.sigma)
    elite_count = max(1, int(round(float(config.population_size) * float(config.elite_fraction))))
    history: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    for generation in range(1, int(config.generations) + 1):
        candidates = []
        for idx in range(int(config.population_size)):
            weights = [float(value) + rng.gauss(0.0, sigma) for value in center]
            result = _run_rl_target_episode(panel, weights, env_config, int(config.hidden_size))
            candidate = {"generation": generation, "candidate": idx, "weights": weights, **result}
            candidates.append(candidate)
        candidates.sort(key=lambda item: float(item["score"]), reverse=True)
        elites = candidates[:elite_count]
        center = [sum(float(item["weights"][j]) for item in elites) / len(elites) for j in range(weight_count)]
        sigma *= float(config.sigma_decay)
        gen_best = candidates[0]
        history.append(
            {
                "generation": generation,
                "sigma": round(sigma, 6),
                "best_score": gen_best["score"],
                "best_return_pct": gen_best["summary"]["total_return_pct"],
                "best_final_equity": gen_best["summary"]["final_equity"],
                "best_max_drawdown_pct": gen_best["summary"]["max_drawdown_pct"],
                "best_trade_count": gen_best["summary"]["trade_count"],
                "mean_elite_score": round(sum(float(item["score"]) for item in elites) / len(elites), 6),
            }
        )
        if best is None or float(gen_best["score"]) > float(best["score"]):
            best = gen_best
        if bool(config.stop_on_target) and float((best or gen_best)["summary"]["total_return_pct"]) >= float(config.target_return_pct):
            break

    best_payload = best or _run_rl_target_episode(panel, center, env_config, int(config.hidden_size))
    return {
        "lab_version": LAB_VERSION,
        "mode": "rl_target_policy_search",
        "config": asdict(config),
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "policy": {
            "features": RL_POLICY_FEATURES,
            "hidden_size": int(config.hidden_size),
            "weight_count": weight_count,
            "best_weights": best_payload.get("weights", center),
            "note": "nonlinear target-weight policy searched by episode reward; actions are target allocation rebalances",
        },
        "history": history,
        "best": {
            "score": best_payload["score"],
            "total_reward": best_payload["total_reward"],
            "summary": best_payload["summary"],
            "trades": best_payload.get("trades", []),
            "actions": best_payload.get("actions", []),
            "equity_curve": best_payload.get("equity_curve", []),
        },
    }


def train_rl_policy_search(
    config: RLTrainerConfig,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    panel = load_intraday_panel(
        config.start_date,
        config.end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(config.max_symbols_per_day),
    )
    env_config = RLTradingEnvConfig(
        budget=float(config.budget),
        max_observation_symbols=int(config.max_observation_symbols),
    )
    rng = random.Random(int(config.seed))
    weight_count = len(RL_POLICY_FEATURES) * 2 + 6
    center = [0.0 for _ in range(weight_count)]
    sigma = float(config.sigma)
    elite_count = max(1, int(round(float(config.population_size) * float(config.elite_fraction))))
    history: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    for generation in range(1, int(config.generations) + 1):
        candidates = []
        for idx in range(int(config.population_size)):
            weights = [float(value) + rng.gauss(0.0, sigma) for value in center]
            result = _run_rl_episode(panel, weights, env_config)
            row = {
                "generation": generation,
                "candidate": idx,
                "weights": weights,
                **result,
            }
            candidates.append(row)
        candidates.sort(key=lambda item: float(item["score"]), reverse=True)
        elites = candidates[:elite_count]
        center = [sum(float(item["weights"][j]) for item in elites) / len(elites) for j in range(weight_count)]
        sigma *= float(config.sigma_decay)
        gen_best = candidates[0]
        history.append(
            {
                "generation": generation,
                "sigma": round(sigma, 6),
                "best_score": gen_best["score"],
                "best_return_pct": gen_best["summary"]["total_return_pct"],
                "best_final_equity": gen_best["summary"]["final_equity"],
                "best_max_drawdown_pct": gen_best["summary"]["max_drawdown_pct"],
                "best_trade_count": gen_best["summary"]["trade_count"],
                "mean_elite_score": round(sum(float(item["score"]) for item in elites) / len(elites), 6),
            }
        )
        if best is None or float(gen_best["score"]) > float(best["score"]):
            best = gen_best

    best_payload = best or _run_rl_episode(panel, center, env_config)
    return {
        "lab_version": LAB_VERSION,
        "mode": "rl_policy_search",
        "config": asdict(config),
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
        },
        "policy": {
            "features": RL_POLICY_FEATURES,
            "weight_count": weight_count,
            "best_weights": best_payload.get("weights", center),
            "note": "linear policy searched by episode reward; not a hand-written strategy DSL",
        },
        "history": history,
        "best": {
            "score": best_payload["score"],
            "total_reward": best_payload["total_reward"],
            "summary": best_payload["summary"],
            "trades": best_payload.get("trades", []),
            "actions": best_payload.get("actions", []),
            "equity_curve": best_payload.get("equity_curve", []),
        },
    }


class MarketReplayEnv:
    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        budget: float = 1_000_000.0,
        costs: Optional[IntradayCostParams] = None,
    ) -> None:
        self.panel = panel.sort_values(["bucket_start", "symbol"]).reset_index(drop=True)
        self.budget = float(budget)
        self.costs = costs or IntradayCostParams()
        self.row_by_symbol_bucket = _row_map(self.panel)
        self.next_bucket_by_symbol_bucket = _next_bucket_map(self.panel)

    def backtest(self, spec: IntradayStrategySpec) -> Dict[str, Any]:
        if self.panel.empty:
            return {
                "lab_version": LAB_VERSION,
                "strategy": asdict(spec),
                "summary": _portfolio_summary([], [], self.budget),
                "trades": [],
                "equity_curve": [],
                "actions": [],
            }

        cash = float(self.budget)
        positions: Dict[str, Dict[str, Any]] = {}
        pending_entries: Dict[str, List[Dict[str, Any]]] = {}
        trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        planned_entries = 0
        filled_entries = 0

        buckets = [str(v) for v in sorted(self.panel["bucket_start"].unique())]
        panel_by_bucket = {str(k): g for k, g in self.panel.groupby("bucket_start", sort=False)}

        def close_position(symbol: str, bucket: str, gross_exit_price: float, reason: str) -> None:
            nonlocal cash
            pos = positions[symbol]
            exit_price = _apply_sell_costs(gross_exit_price, self.costs)
            proceeds = float(pos["shares"]) * exit_price
            cash += proceeds
            invested_cash = float(pos["invested_cash"])
            pnl_cash = proceeds - invested_cash
            net_return_pct = (proceeds / invested_cash - 1.0) * 100.0 if invested_cash else 0.0
            trades.append(
                {
                    "strategy_name": spec.name,
                    "symbol": symbol,
                    "entry_bucket": pos["entry_bucket"],
                    "entry_date": pos["entry_date"],
                    "exit_bucket": bucket,
                    "exit_date": str(bucket)[:10],
                    "gross_entry_price": round(float(pos["gross_entry_price"]), 4),
                    "gross_exit_price": round(float(gross_exit_price), 4),
                    "invested_cash": round(invested_cash, 2),
                    "realized_cash": round(proceeds, 2),
                    "pnl_cash": round(pnl_cash, 2),
                    "net_return_pct": round(net_return_pct, 2),
                    "holding_buckets": int(pos.get("holding_buckets") or 0),
                    "max_runup_pct": round(float(pos.get("max_runup_pct") or 0.0), 2),
                    "max_drawdown_pct": round(float(pos.get("max_drawdown_pct") or 0.0), 2),
                    "exit_reason": reason,
                    "entry_reason": pos.get("entry_reason"),
                    "signal_bucket": pos.get("signal_bucket"),
                    "data_tier": pos.get("data_tier"),
                }
            )
            actions.append({"bucket_start": bucket, "symbol": symbol, "action": "sell", "reason": reason})
            positions.pop(symbol, None)

        for bucket in buckets:
            rows = panel_by_bucket.get(bucket)
            if rows is None or rows.empty:
                continue

            for entry in sorted(pending_entries.pop(bucket, []), key=lambda item: (-float(item["score"]), str(item["symbol"]))):
                symbol = str(entry["symbol"])
                if symbol in positions or len(positions) >= spec.max_positions:
                    continue
                row = self.row_by_symbol_bucket.get((symbol, bucket))
                if row is None or _is_blocked_for_buy(row):
                    continue
                current_exposure = sum(float(pos["invested_cash"]) for pos in positions.values())
                exposure_cap = self.budget * float(spec.max_total_exposure_pct)
                target_cash = min(self.budget * float(spec.position_pct), exposure_cap - current_exposure, cash)
                if target_cash <= 5_000:
                    continue
                gross_entry_price = float(row["open"])
                if gross_entry_price <= 0:
                    continue
                effective_entry = _apply_buy_costs(gross_entry_price, self.costs)
                shares = target_cash / effective_entry
                cash -= target_cash
                positions[symbol] = {
                    "symbol": symbol,
                    "entry_bucket": bucket,
                    "entry_date": str(row["trade_date"]),
                    "gross_entry_price": gross_entry_price,
                    "effective_entry_price": effective_entry,
                    "shares": shares,
                    "invested_cash": target_cash,
                    "holding_buckets": 0,
                    "peak_price": gross_entry_price,
                    "max_runup_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                    "entry_reason": entry.get("reason"),
                    "signal_bucket": entry.get("signal_bucket"),
                    "data_tier": entry.get("data_tier"),
                }
                filled_entries += 1
                actions.append({"bucket_start": bucket, "symbol": symbol, "action": "buy", "reason": entry.get("reason")})

            for symbol, pos in list(positions.items()):
                row = self.row_by_symbol_bucket.get((symbol, bucket))
                if row is None:
                    continue
                pos["holding_buckets"] = int(pos.get("holding_buckets") or 0) + 1
                entry = float(pos["gross_entry_price"])
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                pos["peak_price"] = max(float(pos.get("peak_price") or entry), high)
                pos["max_runup_pct"] = max(float(pos.get("max_runup_pct") or 0.0), ((high / entry) - 1.0) * 100.0 if entry else 0.0)
                pos["max_drawdown_pct"] = min(float(pos.get("max_drawdown_pct") or 0.0), ((low / entry) - 1.0) * 100.0 if entry else 0.0)

                if str(row["trade_date"]) == str(pos["entry_date"]):
                    continue
                if _is_blocked_for_sell(row):
                    continue
                stop_price = entry * (1.0 + float(spec.stop_loss_pct) / 100.0)
                if low <= stop_price:
                    close_position(symbol, bucket, min(float(row["open"]), stop_price) if float(row["open"]) < entry else stop_price, "stop_loss")
                    continue
                take_price = entry * (1.0 + float(spec.take_profit_pct) / 100.0)
                if high >= take_price:
                    close_position(symbol, bucket, take_price, "take_profit")
                    continue
                peak_return = ((float(pos["peak_price"]) / entry) - 1.0) * 100.0 if entry else 0.0
                close_from_peak = ((close / float(pos["peak_price"])) - 1.0) * 100.0 if float(pos["peak_price"]) else 0.0
                if peak_return >= spec.trailing_activate_pct and close_from_peak <= spec.trailing_drawdown_pct:
                    close_position(symbol, bucket, close, "trailing_drawdown")
                    continue
                if int(pos["holding_buckets"]) >= int(spec.max_holding_buckets):
                    close_position(symbol, bucket, close, "max_holding_buckets")
                    continue
                holding_days = len({str(item[:10]) for item in buckets if str(pos["entry_bucket"]) <= str(item) <= bucket})
                if holding_days >= int(spec.max_holding_days):
                    close_position(symbol, bucket, close, "max_holding_days")

            opened_today = sum(1 for pos in positions.values() if str(pos.get("entry_date")) == str(bucket[:10]))
            candidates = []
            for _, row in rows.iterrows():
                ok, score, reason = _entry_signal(row, spec)
                if ok:
                    candidates.append((score, str(row["symbol"]), reason, row))
            candidates.sort(key=lambda item: (-float(item[0]), item[1]))
            for score, symbol, reason, row in candidates:
                if symbol in positions:
                    continue
                if opened_today >= spec.max_new_positions_per_day:
                    break
                next_bucket = self.next_bucket_by_symbol_bucket.get((symbol, bucket))
                if not next_bucket:
                    continue
                pending_entries.setdefault(next_bucket, []).append(
                    {
                        "symbol": symbol,
                        "score": score,
                        "reason": reason,
                        "signal_bucket": bucket,
                        "data_tier": row.get("data_tier"),
                    }
                )
                planned_entries += 1
                opened_today += 1
                actions.append(
                    {
                        "bucket_start": bucket,
                        "symbol": symbol,
                        "action": "plan_buy_next_bucket",
                        "score": score,
                        "reason": reason,
                    }
                )

            equity = cash
            for symbol, pos in positions.items():
                row = self.row_by_symbol_bucket.get((symbol, bucket))
                mark_price = float(row["close"]) if row is not None else float(pos["gross_entry_price"])
                equity += float(pos["shares"]) * mark_price
            equity_curve.append(
                {
                    "bucket_start": bucket,
                    "trade_date": bucket[:10],
                    "cash": round(cash, 2),
                    "equity": round(equity, 2),
                    "open_positions": len(positions),
                }
            )

        if buckets:
            final_bucket = buckets[-1]
            for symbol in list(positions.keys()):
                row = self.row_by_symbol_bucket.get((symbol, final_bucket))
                close_position(symbol, final_bucket, float(row["close"]) if row is not None else float(positions[symbol]["gross_entry_price"]), "window_end_mark")
            if equity_curve:
                equity_curve[-1]["cash"] = round(cash, 2)
                equity_curve[-1]["equity"] = round(cash, 2)
                equity_curve[-1]["open_positions"] = 0

        return {
            "lab_version": LAB_VERSION,
            "strategy": asdict(spec),
            "summary": _portfolio_summary(trades, equity_curve, self.budget, planned_entries=planned_entries, filled_entries=filled_entries),
            "trades": trades,
            "equity_curve": equity_curve,
            "actions": actions,
        }


def _is_blocked_for_buy(row: pd.Series) -> bool:
    if str(row.get("risk_flag_type") or "normal") != "normal":
        return True
    if _safe_float(row.get("is_limit_up_close_5m")) > 0 or _safe_float(row.get("near_limit_up_ratio")) >= 0.997:
        return True
    return False


def _is_blocked_for_sell(row: pd.Series) -> bool:
    if _safe_float(row.get("is_limit_down_close_5m")) > 0 or _safe_float(row.get("near_limit_down_ratio")) >= 0.997:
        return True
    return False


def _entry_signal(row: pd.Series, spec: IntradayStrategySpec) -> Tuple[bool, float, str]:
    bucket_time = str(row.get("bucket_time") or "")[-8:]
    if bucket_time < spec.earliest_entry_time or bucket_time > spec.latest_entry_time:
        return False, 0.0, "outside_entry_window"
    if spec.require_order_book and not bool(row.get("has_order_book")):
        return False, 0.0, "missing_order_book"
    if not _is_mainboard_10cm_symbol(str(row.get("symbol"))):
        return False, 0.0, "not_mainboard_10cm"
    if _is_blocked_for_buy(row):
        return False, 0.0, "blocked_for_buy"
    values = {
        "bucket_amount": _safe_float(row.get("total_amount")),
        "cum_amount": _safe_float(row.get("cum_amount")),
        "return_from_open": _safe_float(row.get("return_from_open_pct")),
        "l2_main": _safe_float(row.get("l2_main_net_ratio")),
        "l2_super": _safe_float(row.get("l2_super_net_ratio")),
        "oib": _safe_float(row.get("oib_ratio")),
        "cvd": _safe_float(row.get("cvd_ratio")),
        "book": _safe_float(row.get("book_imbalance_ratio")),
        "price_vs_vwap": _safe_float(row.get("price_vs_vwap_pct")),
    }
    if values["bucket_amount"] < spec.min_bucket_amount:
        return False, 0.0, "bucket_amount_low"
    if values["cum_amount"] < spec.min_cum_amount:
        return False, 0.0, "cum_amount_low"
    if values["return_from_open"] < spec.min_return_from_open_pct or values["return_from_open"] > spec.max_return_from_open_pct:
        return False, 0.0, "return_window_fail"
    if values["l2_main"] < spec.min_l2_main_ratio:
        return False, 0.0, "l2_main_weak"
    if values["l2_super"] < spec.min_l2_super_ratio:
        return False, 0.0, "l2_super_weak"
    if values["oib"] < spec.min_oib_ratio:
        return False, 0.0, "oib_weak"
    if values["cvd"] < spec.min_cvd_ratio:
        return False, 0.0, "cvd_weak"
    if values["book"] < spec.min_book_imbalance:
        return False, 0.0, "book_weak"
    if values["price_vs_vwap"] < spec.min_price_vs_vwap_pct:
        return False, 0.0, "below_vwap"
    score = (
        35.0 * _clip((values["l2_main"] - spec.min_l2_main_ratio) / 0.05, 0.0, 1.0)
        + 18.0 * _clip((values["l2_super"] - spec.min_l2_super_ratio) / 0.03, 0.0, 1.0)
        + 15.0 * _clip((values["oib"] - spec.min_oib_ratio) / 0.04, 0.0, 1.0)
        + 12.0 * _clip((values["book"] - spec.min_book_imbalance) / 0.8, 0.0, 1.0)
        + 10.0 * _clip(values["price_vs_vwap"] / 2.0, 0.0, 1.0)
        + 10.0 * _clip(values["return_from_open"] / max(spec.max_return_from_open_pct, 1.0), 0.0, 1.0)
    )
    return True, round(score, 4), "5m_l2_order_book_signal"


def make_seed_strategy(data_tier: str = "full_l2_order_book") -> IntradayStrategySpec:
    require_order_book = data_tier == "full_l2_order_book"
    return IntradayStrategySpec(
        name=f"seed_{data_tier}",
        data_tier=data_tier,
        require_order_book=require_order_book,
        min_bucket_amount=8_000_000.0 if require_order_book else 6_000_000.0,
        min_cum_amount=60_000_000.0 if require_order_book else 45_000_000.0,
        min_l2_main_ratio=0.006,
        min_l2_super_ratio=0.0,
        min_oib_ratio=-0.002 if require_order_book else -1.0,
        min_cvd_ratio=-0.002 if require_order_book else -1.0,
        min_book_imbalance=-0.05 if require_order_book else -1.0,
    )


def _random_spec(rng: random.Random, idx: int, data_tier: str) -> IntradayStrategySpec:
    require_order_book = data_tier == "full_l2_order_book"
    return IntradayStrategySpec(
        name=f"evo_{data_tier}_{idx:04d}",
        data_tier=data_tier,
        require_order_book=require_order_book,
        earliest_entry_time=rng.choice(["09:35:00", "09:40:00", "09:45:00", "10:00:00"]),
        latest_entry_time=rng.choice(["13:45:00", "14:00:00", "14:20:00", "14:35:00"]),
        max_positions=rng.choice([2, 3, 4, 5]),
        max_new_positions_per_day=rng.choice([1, 2, 3]),
        position_pct=rng.choice([0.12, 0.16, 0.20, 0.24]),
        max_total_exposure_pct=rng.choice([0.45, 0.60, 0.75, 0.90]),
        min_bucket_amount=rng.uniform(4_000_000, 18_000_000),
        min_cum_amount=rng.uniform(35_000_000, 120_000_000),
        min_return_from_open_pct=rng.uniform(-0.8, 1.6),
        max_return_from_open_pct=rng.uniform(4.5, 9.2),
        min_l2_main_ratio=rng.uniform(-0.004, 0.018),
        min_l2_super_ratio=rng.uniform(-0.006, 0.01),
        min_oib_ratio=rng.uniform(-0.008, 0.012) if require_order_book else -1.0,
        min_cvd_ratio=rng.uniform(-0.008, 0.012) if require_order_book else -1.0,
        min_book_imbalance=rng.uniform(-0.25, 0.25) if require_order_book else -1.0,
        min_price_vs_vwap_pct=rng.uniform(-1.2, 0.8),
        stop_loss_pct=rng.uniform(-8.0, -3.8),
        take_profit_pct=rng.uniform(5.0, 14.0),
        trailing_activate_pct=rng.uniform(5.0, 12.0),
        trailing_drawdown_pct=rng.uniform(-7.0, -3.0),
        max_holding_buckets=rng.choice([36, 48, 72, 96, 144]),
        max_holding_days=rng.choice([2, 3, 4, 6, 8]),
    )


def _mutate_spec(spec: IntradayStrategySpec, rng: random.Random, idx: int, mutation_rate: float) -> IntradayStrategySpec:
    raw = asdict(spec)
    raw["name"] = f"{spec.name}_m{idx:03d}"
    numeric_ranges = {
        "min_bucket_amount": (3_000_000, 22_000_000, 2_000_000),
        "min_cum_amount": (25_000_000, 150_000_000, 10_000_000),
        "min_return_from_open_pct": (-1.5, 2.5, 0.4),
        "max_return_from_open_pct": (3.0, 10.0, 0.6),
        "min_l2_main_ratio": (-0.008, 0.025, 0.004),
        "min_l2_super_ratio": (-0.01, 0.015, 0.003),
        "min_oib_ratio": (-0.012, 0.02, 0.004),
        "min_cvd_ratio": (-0.012, 0.02, 0.004),
        "min_book_imbalance": (-0.35, 0.35, 0.08),
        "min_price_vs_vwap_pct": (-1.8, 1.2, 0.3),
        "stop_loss_pct": (-9.0, -3.0, 0.8),
        "take_profit_pct": (4.0, 18.0, 1.0),
        "trailing_activate_pct": (4.0, 16.0, 1.0),
        "trailing_drawdown_pct": (-8.5, -2.5, 0.8),
        "position_pct": (0.08, 0.28, 0.03),
        "max_total_exposure_pct": (0.35, 0.95, 0.08),
    }
    for key, (low, high, scale) in numeric_ranges.items():
        if key in {"min_oib_ratio", "min_cvd_ratio", "min_book_imbalance"} and not spec.require_order_book:
            continue
        if rng.random() <= mutation_rate:
            raw[key] = _clip(float(raw[key]) + rng.uniform(-scale, scale), low, high)
    for key, choices in {
        "max_positions": [2, 3, 4, 5],
        "max_new_positions_per_day": [1, 2, 3],
        "max_holding_buckets": [36, 48, 72, 96, 144],
        "max_holding_days": [2, 3, 4, 6, 8],
        "earliest_entry_time": ["09:35:00", "09:40:00", "09:45:00", "10:00:00"],
        "latest_entry_time": ["13:45:00", "14:00:00", "14:20:00", "14:35:00"],
    }.items():
        if rng.random() <= mutation_rate:
            raw[key] = rng.choice(choices)
    return IntradayStrategySpec(**raw)


def _walk_forward_splits(
    trade_dates: Sequence[str],
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int,
) -> List[Dict[str, Any]]:
    dates = list(dict.fromkeys(str(d) for d in trade_dates))
    min_len = train_days + validation_days + test_days
    if len(dates) < min_len:
        return [
            {
                "train_start": dates[0],
                "train_end": dates[-1],
                "validation_start": dates[0],
                "validation_end": dates[-1],
                "test_start": dates[0],
                "test_end": dates[-1],
                "is_short_range_overlap": True,
            }
        ] if dates else []
    out: List[Dict[str, str]] = []
    start = 0
    while start + min_len <= len(dates):
        train_start = dates[start]
        train_end = dates[start + train_days - 1]
        validation_start = dates[start + train_days]
        validation_end = dates[start + train_days + validation_days - 1]
        test_start = dates[start + train_days + validation_days]
        test_end = dates[start + min_len - 1]
        out.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "test_start": test_start,
                "test_end": test_end,
                "is_short_range_overlap": False,
            }
        )
        start += max(1, step_days)
    return out


def _slice_panel(panel: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    return panel[(panel["trade_date"] >= start_date) & (panel["trade_date"] <= end_date)].copy()


def _strategy_score(summary: Dict[str, Any]) -> float:
    return (
        float(summary.get("total_return_pct") or 0.0)
        - abs(float(summary.get("max_drawdown_pct") or 0.0)) * 0.45
        + min(float(summary.get("profit_factor") or 0.0), 5.0) * 0.9
        + min(float(summary.get("trade_count") or 0.0), 30.0) * 0.04
        - float(summary.get("big_loss_le_-7pct") or 0.0) * 0.6
    )


def evaluate_strategy_walk_forward(
    panel: pd.DataFrame,
    spec: IntradayStrategySpec,
    folds: Sequence[Dict[str, str]],
    *,
    budget: float,
) -> Dict[str, Any]:
    fold_rows: List[Dict[str, Any]] = []
    all_test_trades: List[Dict[str, Any]] = []
    for idx, fold in enumerate(folds, start=1):
        train_panel = _slice_panel(panel, fold["train_start"], fold["train_end"])
        validation_panel = _slice_panel(panel, fold["validation_start"], fold["validation_end"])
        test_panel = _slice_panel(panel, fold["test_start"], fold["test_end"])
        train_result = MarketReplayEnv(train_panel, budget=budget).backtest(spec)
        validation_result = MarketReplayEnv(validation_panel, budget=budget).backtest(spec)
        test_result = MarketReplayEnv(test_panel, budget=budget).backtest(spec)
        train_summary = train_result["summary"]
        validation_summary = validation_result["summary"]
        test_summary = test_result["summary"]
        validation_score = round(_strategy_score(validation_summary), 4)
        test_score = round(_strategy_score(test_summary), 4)
        fold_rows.append(
            {
                "fold": idx,
                **fold,
                "train_return_pct": train_summary["total_return_pct"],
                "train_max_drawdown_pct": train_summary["max_drawdown_pct"],
                "train_trade_count": train_summary["trade_count"],
                "validation_return_pct": validation_summary["total_return_pct"],
                "validation_max_drawdown_pct": validation_summary["max_drawdown_pct"],
                "validation_trade_count": validation_summary["trade_count"],
                "validation_win_rate_pct": validation_summary["win_rate_pct"],
                "validation_profit_factor": validation_summary["profit_factor"],
                "test_return_pct": test_summary["total_return_pct"],
                "test_max_drawdown_pct": test_summary["max_drawdown_pct"],
                "test_trade_count": test_summary["trade_count"],
                "test_win_rate_pct": test_summary["win_rate_pct"],
                "test_profit_factor": test_summary["profit_factor"],
                "score": validation_score,
                "validation_score": validation_score,
                "test_score": test_score,
            }
        )
        for trade in test_result["trades"]:
            all_test_trades.append({"fold": idx, **trade})
    if not fold_rows:
        aggregate = _portfolio_summary([], [], budget)
    else:
        df = pd.DataFrame(fold_rows)
        aggregate = {
            "fold_count": int(len(fold_rows)),
            "mean_train_return_pct": round(float(df["train_return_pct"].mean()), 2),
            "mean_validation_return_pct": round(float(df["validation_return_pct"].mean()), 2),
            "min_validation_return_pct": round(float(df["validation_return_pct"].min()), 2),
            "mean_test_return_pct": round(float(df["test_return_pct"].mean()), 2),
            "min_test_return_pct": round(float(df["test_return_pct"].min()), 2),
            "mean_validation_max_drawdown_pct": round(float(df["validation_max_drawdown_pct"].mean()), 2),
            "worst_validation_max_drawdown_pct": round(float(df["validation_max_drawdown_pct"].min()), 2),
            "mean_max_drawdown_pct": round(float(df["test_max_drawdown_pct"].mean()), 2),
            "worst_max_drawdown_pct": round(float(df["test_max_drawdown_pct"].min()), 2),
            "total_validation_trade_count": int(df["validation_trade_count"].sum()),
            "total_trade_count": int(df["test_trade_count"].sum()),
            "mean_validation_win_rate_pct": round(float(df["validation_win_rate_pct"].mean()), 2),
            "mean_win_rate_pct": round(float(df["test_win_rate_pct"].mean()), 2),
            "mean_validation_profit_factor": round(float(df["validation_profit_factor"].replace(999.0, 5.0).mean()), 3),
            "mean_profit_factor": round(float(df["test_profit_factor"].replace(999.0, 5.0).mean()), 3),
            "mean_score": round(float(df["score"].mean()), 4),
            "mean_test_score": round(float(df["test_score"].mean()), 4),
            "short_range_overlap_folds": int(df["is_short_range_overlap"].sum()) if "is_short_range_overlap" in df.columns else 0,
        }
    return {
        "strategy": asdict(spec),
        "aggregate": aggregate,
        "folds": fold_rows,
        "test_trades": all_test_trades,
    }


def run_evolution_arena(
    config: EvolutionConfig,
    *,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    panel = load_intraday_panel(
        config.start_date,
        config.end_date,
        db_path=db_path,
        symbols=symbols,
        max_symbols_per_day=int(config.max_symbols_per_day),
    )
    dates = sorted(panel["trade_date"].unique().tolist()) if not panel.empty else []
    folds = _walk_forward_splits(
        dates,
        train_days=int(config.train_days),
        validation_days=int(config.validation_days),
        test_days=int(config.test_days),
        step_days=int(config.step_days),
    )
    rng = random.Random(int(config.seed))
    population = [make_seed_strategy(config.data_tier)]
    population.extend(_random_spec(rng, idx, config.data_tier) for idx in range(max(0, int(config.population_size) - 1)))
    generation_rows: List[Dict[str, Any]] = []
    evaluated: Dict[str, Dict[str, Any]] = {}

    for generation in range(1, int(config.generations) + 1):
        generation_results: List[Dict[str, Any]] = []
        for spec in population:
            result = evaluate_strategy_walk_forward(panel, spec, folds, budget=float(config.budget))
            result["generation"] = generation
            evaluated[spec.name] = result
            aggregate = result["aggregate"]
            generation_results.append(result)
            generation_rows.append(
                {
                    "generation": generation,
                    "strategy_name": spec.name,
                    **aggregate,
                    "strategy": asdict(spec),
                }
            )
        generation_results.sort(key=lambda item: float(item["aggregate"].get("mean_score") or -9999), reverse=True)
        elites = [IntradayStrategySpec(**item["strategy"]) for item in generation_results[: max(1, int(config.elite_size))]]
        next_population = elites[:]
        idx = 0
        while len(next_population) < int(config.population_size):
            parent = rng.choice(elites)
            next_population.append(_mutate_spec(parent, rng, idx, float(config.mutation_rate)))
            idx += 1
        population = next_population

    leaderboard = sorted(generation_rows, key=lambda row: float(row.get("mean_score") or -9999), reverse=True)
    best_name = str(leaderboard[0]["strategy_name"]) if leaderboard else ""
    best_result = evaluated.get(best_name, {}) if best_name else {}
    return {
        "lab_version": LAB_VERSION,
        "config": asdict(config),
        "data": {
            "atomic_db_path": db_path or resolve_selection_v2_atomic_db_path(),
            "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
            "rows": int(len(panel)),
            "trade_dates": dates,
            "folds": folds,
        },
        "leaderboard": leaderboard,
        "best": best_result,
        "raw_extract_policy": "not used; this arena reads processed atomic_*_5m tables only",
        "universe_policy": "mainboard_10cm_symbols_ranked_by_previous_trade_date_amount unless --symbols is supplied",
    }


def write_arena_outputs(payload: Dict[str, Any], out_dir: str | Path) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "arena_summary.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    written = {"json": str(json_path)}
    leaderboard = payload.get("leaderboard") or []
    if leaderboard:
        rows = []
        for item in leaderboard:
            row = {k: v for k, v in item.items() if k != "strategy"}
            rows.append(row)
        leaderboard_path = out / "leaderboard.csv"
        pd.DataFrame(rows).to_csv(leaderboard_path, index=False)
        written["leaderboard_csv"] = str(leaderboard_path)
    trades = (payload.get("best") or {}).get("test_trades") or []
    if trades:
        trades_path = out / "best_test_trades.csv"
        pd.DataFrame(trades).to_csv(trades_path, index=False)
        written["best_trades_csv"] = str(trades_path)
    md_path = out / "README.md"
    md_path.write_text(_render_arena_markdown(payload), encoding="utf-8")
    written["markdown"] = str(md_path)
    return written


def _render_arena_markdown(payload: Dict[str, Any]) -> str:
    config = payload.get("config") or {}
    data = payload.get("data") or {}
    best = payload.get("best") or {}
    best_agg = best.get("aggregate") or {}
    lines = [
        "# 5分钟伪日内自进化实验室",
        "",
        f"- 版本：{payload.get('lab_version')}",
        f"- 区间：{config.get('start_date')} ~ {config.get('end_date')}",
        f"- 数据口径：{config.get('data_tier')}",
        f"- 选优口径：validation 排名；test 只做最终报告",
        f"- T+1：强制开启；同日买入不可同日卖出",
        f"- 股票数：{data.get('symbols')}，5m行数：{data.get('rows')}",
        f"- 股票池：上一交易日成交额 TopN 预选；不使用当日收盘后成交额",
        f"- raw解压：不使用；仅读 processed atomic_*_5m",
        f"- 短区间重叠fold：{best_agg.get('short_range_overlap_folds', 0)}",
        "",
        "## 最优策略",
        "",
        f"- 名称：`{(best.get('strategy') or {}).get('name')}`",
        f"- 平均验证收益：{best_agg.get('mean_validation_return_pct')}%",
        f"- 平均测试收益：{best_agg.get('mean_test_return_pct')}%",
        f"- 最差测试收益：{best_agg.get('min_test_return_pct')}%",
        f"- 测试平均回撤：{best_agg.get('mean_max_drawdown_pct')}%",
        f"- 测试交易数：{best_agg.get('total_trade_count')}",
        f"- 验证得分：{best_agg.get('mean_score')}",
        "",
        "## 排行榜 Top 10",
        "",
        "| rank | generation | strategy | val_score | val_return | test_return | worst_test_dd | test_trades |",
        "|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate((payload.get("leaderboard") or [])[:10], start=1):
        lines.append(
            f"| {rank} | {row.get('generation')} | `{row.get('strategy_name')}` | {row.get('mean_score')} | "
            f"{row.get('mean_validation_return_pct')} | {row.get('mean_test_return_pct')} | "
            f"{row.get('worst_max_drawdown_pct')} | {row.get('total_trade_count')} |"
        )
    return "\n".join(lines) + "\n"


def write_catalog_output(payload: Dict[str, Any], out_path: str | Path) -> str:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


DEFAULT_PPO_REPORT_PATH = DEFAULT_OUTPUT_DIR / "two_stage_joint_objective_report.json"


def _load_symbol_name_map() -> Dict[str, str]:
    def _merge_from_db(name_map: Dict[str, str], db_path: str, tables: Sequence[str]) -> None:
        if not db_path or not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                for table in tables:
                    try:
                        rows = conn.execute(f"SELECT symbol, name FROM {table}").fetchall()
                    except Exception:
                        continue
                    for row in rows:
                        symbol = str(row[0] or "").lower().strip()
                        name = str(row[1] or "").strip()
                        if not symbol or not name:
                            continue
                        if name.lower() in {symbol.lower(), "nan"}:
                            continue
                        if symbol not in name_map or name_map[symbol].lower() == symbol:
                            name_map[symbol] = name
            finally:
                conn.close()
        except Exception:
            return

    name_map: Dict[str, str] = {}
    candidates: List[Tuple[str, Sequence[str]]] = []
    try:
        from backend.app.core.config import DEFAULT_FORMAL_MARKET_DATA_ROOT

        root = DEFAULT_FORMAL_MARKET_DATA_ROOT
        candidates.extend(
            [
                (os.path.join(root, "market_data.db"), ("stock_universe_meta",)),
                (os.path.join(root, "user_data.db"), ("watchlist",)),
                (os.path.join(root, "market_heat", "stock_sector_map.db"), ("stock_sector_memberships",)),
                (os.path.join(root, "market_heat", "tradable_theme_map.db"), ("clean_stock_sector_memberships", "tradable_theme_memberships")),
                (os.path.join(root, "market_heat", "fine_theme_heat_daily.db"), ("fine_theme_member_daily",)),
                (os.path.join(root, "market_heat", "hot_theme_low_position_l2_samples.db"), ("samples",)),
                ("data/market_data.db", ("stock_universe_meta",)),
                ("data/user_data.db", ("watchlist",)),
                ("data/market_heat/stock_sector_map.db", ("stock_sector_memberships",)),
                ("data/market_heat/tradable_theme_map.db", ("clean_stock_sector_memberships", "tradable_theme_memberships")),
            ]
        )
    except Exception:
        candidates.extend(
            [
                ("data/market_data.db", ("stock_universe_meta",)),
                ("data/user_data.db", ("watchlist",)),
                ("data/market_heat/stock_sector_map.db", ("stock_sector_memberships",)),
                ("data/market_heat/tradable_theme_map.db", ("clean_stock_sector_memberships", "tradable_theme_memberships")),
            ]
        )

    for db_path, tables in candidates:
        _merge_from_db(name_map, db_path, tables)
    return name_map


def _normalize_ppo_report_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    trades = list(payload.get("trades") or [])
    actions = list(payload.get("actions") or [])
    equity_curve = list(payload.get("equity_curve") or [])
    symbol_names = _load_symbol_name_map()

    by_symbol: Dict[str, Dict[str, Any]] = {}
    by_day: Dict[str, Dict[str, Any]] = {}
    for trade in trades:
        symbol = str(trade.get("symbol") or "").lower()
        if not symbol:
            continue
        bucket = by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "name": symbol_names.get(symbol) or symbol,
                "trade_count": 0,
                "pnl_cash": 0.0,
                "realized_cash": 0.0,
                "invested_cash": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "win_count": 0,
                "loss_count": 0,
                "max_return_pct": None,
                "min_return_pct": None,
                "entry_dates": [],
                "exit_dates": [],
            },
        )
        bucket["trade_count"] += 1
        bucket["pnl_cash"] += float(trade.get("pnl_cash") or 0.0)
        bucket["realized_cash"] += float(trade.get("realized_cash") or 0.0)
        bucket["invested_cash"] += float(trade.get("cost_cash") or 0.0)
        if float(trade.get("pnl_cash") or 0.0) > 0:
            bucket["win_count"] += 1
        elif float(trade.get("pnl_cash") or 0.0) < 0:
            bucket["loss_count"] += 1
        if float(trade.get("sold_fraction") or 0.0) >= 0:
            bucket["sell_count"] += 1
        bucket["entry_dates"].append(str(trade.get("entry_date") or ""))
        bucket["exit_dates"].append(str(trade.get("exit_date") or ""))
        net_return = trade.get("net_return_pct")
        if net_return is not None:
            net_return = float(net_return)
            bucket["max_return_pct"] = net_return if bucket["max_return_pct"] is None else max(float(bucket["max_return_pct"]), net_return)
            bucket["min_return_pct"] = net_return if bucket["min_return_pct"] is None else min(float(bucket["min_return_pct"]), net_return)
        day = str(trade.get("exit_date") or trade.get("entry_date") or "")
        if day:
            day_bucket = by_day.setdefault(
                day,
                {
                    "date": day,
                    "trade_count": 0,
                    "pnl_cash": 0.0,
                    "realized_cash": 0.0,
                    "open_count": 0,
                    "close_count": 0,
                },
            )
            day_bucket["trade_count"] += 1
            day_bucket["pnl_cash"] += float(trade.get("pnl_cash") or 0.0)
            day_bucket["realized_cash"] += float(trade.get("realized_cash") or 0.0)
            day_bucket["close_count"] += 1
    for action in actions:
        if str(action.get("action") or "").lower() == "buy":
            symbol = str(action.get("symbol") or "").lower()
            if symbol in by_symbol:
                by_symbol[symbol]["buy_count"] += 1
    if not any(str(action.get("action") or "").lower() == "buy" for action in actions):
        for bucket in by_symbol.values():
            bucket["buy_count"] = max(int(bucket.get("buy_count") or 0), int(bucket.get("trade_count") or 0))
    symbol_rows = sorted(
        by_symbol.values(),
        key=lambda item: abs(float(item.get("pnl_cash") or 0.0)),
        reverse=True,
    )
    day_rows = sorted(
        by_day.values(),
        key=lambda item: str(item.get("date") or ""),
    )
    return {
        "lab_version": payload.get("lab_version") or LAB_VERSION,
        "mode": payload.get("mode"),
        "model_path": payload.get("model_path"),
        "range": payload.get("range"),
        "data": payload.get("data"),
        "training": payload.get("training"),
        "summary": summary,
        "total_reward": payload.get("total_reward"),
        "steps": payload.get("steps"),
        "policy_note": payload.get("policy_note"),
        "feature_names": payload.get("feature_names") or [],
        "trades": trades,
        "actions": actions,
        "equity_curve": equity_curve,
        "symbol_names": symbol_names,
        "by_symbol": symbol_rows,
        "by_day": day_rows,
    }


def load_ppo_report_payload(report_path: str | Path | None = DEFAULT_PPO_REPORT_PATH) -> Dict[str, Any]:
    path = Path(report_path or DEFAULT_PPO_REPORT_PATH)
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_ppo_report_payload(payload)
    normalized["report_path"] = str(path)
    return normalized
