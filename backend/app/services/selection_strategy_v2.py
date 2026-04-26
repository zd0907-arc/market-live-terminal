from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from backend.app.core.config import DB_FILE, USER_DB_FILE, candidate_atomic_db_paths

DEFAULT_MARKET_DATA_ROOT = "/Users/dong/Desktop/AIGC/market-data"
DEFAULT_FORMAL_MAIN_DB = os.path.join(DEFAULT_MARKET_DATA_ROOT, "market_data.db")
DEFAULT_FORMAL_USER_DB = os.path.join(DEFAULT_MARKET_DATA_ROOT, "user_data.db")
DEFAULT_FORMAL_ATOMIC_DB = os.path.join(
    DEFAULT_MARKET_DATA_ROOT,
    "atomic_facts",
    "market_atomic_mainboard_full_reverse.db",
)
STRATEGY_VERSION_V2 = "selection_strategy_v2_lifecycle"
THEME_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "算力": ("算力", "服务器", "租赁", "gpu", "a800", "智算", "数据中心"),
    "AI": ("ai", "人工智能", "大模型", "训练", "推理"),
    "消费电子": ("消费电子", "电视", "背板", "面板", "显示"),
    "业绩": ("业绩", "利润", "净利润", "扣非", "财报", "季报", "年报", "预增"),
    "订单": ("订单", "中标", "合同", "签约"),
    "政策": ("政策", "补贴", "规划", "通知", "方案"),
}


def build_selection_v2_page_params() -> "SelectionV2Params":
    return SelectionV2Params(
        attack_score_min=65.0,
        repair_score_min=60.0,
        distribution_score_warn=70.0,
        panic_distribution_score_exit=80.0,
        entry_attack_cvd_floor=-0.08,
        entry_return_20d_cap=80.0,
    )


@dataclass(frozen=True)
class SelectionV2Params:
    min_amount: float = 300_000_000.0
    amount_anomaly_launch: float = 1.5
    amount_anomaly_event: float = 1.8
    breakout_threshold_pct: float = 1.0
    l2_main_net_ratio_launch: float = 0.02
    l2_super_net_ratio_launch: float = 0.01
    active_buy_strength_launch: float = 2.0
    positive_l2_bar_ratio_min: float = 0.55
    accumulation_main_net_5d: float = 0.0
    support_pressure_spread_min: float = 0.0
    shakeout_drop_pct: float = -5.0
    shakeout_repair_coverage: float = 0.8
    second_wave_amount_anomaly: float = 1.2
    high_return_20d_pct: float = 25.0
    accumulation_score_min: float = 55.0
    attack_score_min: float = 60.0
    repair_score_min: float = 55.0
    distribution_score_warn: float = 60.0
    panic_distribution_score_exit: float = 70.0
    entry_attack_cvd_floor: float = -0.08
    entry_return_20d_cap: float = 80.0
    distribution_main_net_ratio: float = -0.01
    distribution_support_spread: float = -0.02
    distribution_confirm_days: int = 2
    limit_up_pct: float = 9.5
    limit_down_pct: float = -9.5
    buy_slippage_bp: float = 15.0
    sell_slippage_bp: float = 15.0
    round_trip_fee_bp: float = 20.0
    max_open_positions: int = 3
    max_new_positions_per_day: int = 1
    stop_loss_pct: float = -8.0
    max_holding_days: int = 40


def _candidate_v2_atomic_paths() -> List[str]:
    configured = candidate_atomic_db_paths()
    extra = [os.getenv("SELECTION_V2_ATOMIC_DB_PATH", "").strip()]
    if os.path.exists(DEFAULT_FORMAL_ATOMIC_DB):
        extra.append(DEFAULT_FORMAL_ATOMIC_DB)
    out: List[str] = []
    seen = set()
    for raw in [*extra, *configured]:
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def resolve_selection_v2_atomic_db_path() -> str:
    for path in _candidate_v2_atomic_paths():
        if os.path.exists(path):
            return path
    raise FileNotFoundError("No atomic database found for selection strategy v2")


def _candidate_v2_main_db_paths() -> List[str]:
    candidates = [
        os.getenv("SELECTION_V2_MAIN_DB_PATH", "").strip(),
        os.getenv("DB_PATH", "").strip(),
        DEFAULT_FORMAL_MAIN_DB,
        DB_FILE,
    ]
    out: List[str] = []
    seen = set()
    for raw in candidates:
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def resolve_selection_v2_main_db_path() -> str:
    for path in _candidate_v2_main_db_paths():
        if os.path.exists(path):
            return path
    raise FileNotFoundError("No main database found for selection strategy v2")


def _candidate_v2_user_db_paths() -> List[str]:
    candidates = [
        os.getenv("SELECTION_V2_USER_DB_PATH", "").strip(),
        os.getenv("USER_DB_PATH", "").strip(),
        DEFAULT_FORMAL_USER_DB,
        USER_DB_FILE,
    ]
    out: List[str] = []
    seen = set()
    for raw in candidates:
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def resolve_selection_v2_user_db_path() -> Optional[str]:
    for path in _candidate_v2_user_db_paths():
        if os.path.exists(path):
            return path
    return None


def _atomic_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or resolve_selection_v2_atomic_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _main_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or resolve_selection_v2_main_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = pd.to_numeric(denominator, errors="coerce").replace(0, pd.NA)
    values = pd.to_numeric(numerator, errors="coerce") / denom
    return values.fillna(0.0)


def _clip(value: Optional[float], low: float = 0.0, high: float = 1.0) -> float:
    if value is None or pd.isna(value):
        return low
    return max(low, min(high, float(value)))


def _subscore_linear(value: Optional[float], low: float, high: float) -> float:
    if value is None or pd.isna(value) or high == low:
        return 0.0
    return _clip((float(value) - low) / (high - low))


def _score_linear_100(value: Optional[float], low: float, high: float) -> float:
    return round(100.0 * _subscore_linear(value, low, high), 2)


def load_atomic_daily_window(
    start_date: str,
    end_date: str,
    *,
    symbols: Optional[Sequence[str]] = None,
    db_path: Optional[str] = None,
) -> pd.DataFrame:
    conditions = ["t.trade_date >= ?", "t.trade_date <= ?"]
    params: List[Any] = [start_date, end_date]
    if symbols:
        normalized = [str(symbol).strip().lower() for symbol in symbols if str(symbol).strip()]
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
            o.order_event_count
        FROM atomic_trade_daily AS t
        LEFT JOIN atomic_order_daily AS o
          ON o.symbol = t.symbol
         AND o.trade_date = t.trade_date
        WHERE {where}
        ORDER BY lower(t.symbol) ASC, t.trade_date ASC
    """
    with _atomic_connection(db_path) as conn:
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
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    return df


def compute_v2_metrics(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df.copy()
    feature_frames: List[pd.DataFrame] = []
    for _, group in raw_df.groupby("symbol", sort=False):
        g = group.sort_values("trade_date").copy()
        g["prev_close"] = g["close"].shift(1)
        g["return_1d_pct"] = ((g["close"] / g["prev_close"]) - 1.0) * 100.0
        g["return_3d_pct"] = ((g["close"] / g["close"].shift(3)) - 1.0) * 100.0
        g["return_5d_pct"] = ((g["close"] / g["close"].shift(5)) - 1.0) * 100.0
        g["return_10d_pct"] = ((g["close"] / g["close"].shift(10)) - 1.0) * 100.0
        g["return_20d_pct"] = ((g["close"] / g["close"].shift(20)) - 1.0) * 100.0
        g["amount_ma20"] = g["total_amount"].rolling(20, min_periods=5).mean()
        g["volume_ma20"] = g["total_volume"].rolling(20, min_periods=5).mean()
        g["trade_count_ma20"] = g["trade_count"].rolling(20, min_periods=5).mean()
        g["amount_anomaly_20d"] = _safe_ratio(g["total_amount"], g["amount_ma20"])
        g["volume_anomaly_20d"] = _safe_ratio(g["total_volume"], g["volume_ma20"])
        g["trade_count_anomaly_20d"] = _safe_ratio(g["trade_count"], g["trade_count_ma20"])
        prev20_high = g["close"].shift(1).rolling(20, min_periods=5).max()
        recent20_high = g["close"].rolling(20, min_periods=5).max()
        g["breakout_vs_prev20_high_pct"] = ((g["close"] / prev20_high) - 1.0) * 100.0
        g["max_drawdown_from_20d_high_pct"] = ((g["close"] / recent20_high) - 1.0) * 100.0
        low20 = g["close"].rolling(20, min_periods=5).min()
        low60 = g["close"].rolling(60, min_periods=10).min()
        high20 = g["close"].rolling(20, min_periods=5).max()
        high60 = g["close"].rolling(60, min_periods=10).max()
        g["price_position_20d"] = _safe_ratio(g["close"] - low20, (high20 - low20))
        g["price_position_60d"] = _safe_ratio(g["close"] - low60, (high60 - low60))
        g["l2_main_net_ratio"] = _safe_ratio(g["l2_main_net_amount"], g["total_amount"])
        g["l2_super_net_ratio"] = _safe_ratio(g["l2_super_net_amount"], g["total_amount"])
        g["l1_l2_divergence"] = g["l2_main_net_amount"] - g["l1_main_net_amount"]
        g["main_net_3d"] = g["l2_main_net_amount"].rolling(3, min_periods=1).sum()
        g["super_net_3d"] = g["l2_super_net_amount"].rolling(3, min_periods=1).sum()
        g["main_net_5d"] = g["l2_main_net_amount"].rolling(5, min_periods=1).sum()
        g["super_net_5d"] = g["l2_super_net_amount"].rolling(5, min_periods=1).sum()
        g["active_buy_strength"] = g["l2_buy_ratio"] - g["l2_sell_ratio"]
        positive_total = g["positive_l2_net_bar_count"] + g["negative_l2_net_bar_count"]
        g["positive_l2_bar_ratio"] = _safe_ratio(g["positive_l2_net_bar_count"], positive_total)
        g["order_imbalance_ratio"] = _safe_ratio(g["oib_delta_amount"], g["total_amount"])
        g["cvd_ratio"] = _safe_ratio(g["cvd_delta_amount"], g["total_amount"])
        g["add_buy_ratio"] = _safe_ratio(g["add_buy_amount"], g["total_amount"])
        g["add_sell_ratio"] = _safe_ratio(g["add_sell_amount"], g["total_amount"])
        g["cancel_buy_ratio"] = _safe_ratio(g["cancel_buy_amount"], g["total_amount"])
        g["cancel_sell_ratio"] = _safe_ratio(g["cancel_sell_amount"], g["total_amount"])
        g["support_pressure_spread"] = g["buy_support_ratio"] - g["sell_pressure_ratio"]
        g["prior_3d_min_return_1d_pct"] = g["return_1d_pct"].shift(1).rolling(3, min_periods=1).min()
        g["prior_3d_min_l2_main_net"] = g["l2_main_net_amount"].shift(1).rolling(3, min_periods=1).min()
        g["prior_3d_min_l2_super_net"] = g["l2_super_net_amount"].shift(1).rolling(3, min_periods=1).min()
        feature_frames.append(g)
    metrics_df = pd.concat(feature_frames, ignore_index=True)
    metrics_df["trade_date"] = pd.to_datetime(metrics_df["trade_date"]).dt.strftime("%Y-%m-%d")
    return metrics_df


def _compute_intent_profile(row: pd.Series, params: SelectionV2Params) -> Dict[str, Any]:
    accumulation_score = round(
        0.28 * _score_linear_100(row.get("main_net_5d", 0.0), 0.0, max(float(row.get("total_amount", 0.0)) * 0.15, 1.0))
        + 0.22 * _score_linear_100(row.get("positive_l2_bar_ratio"), 0.45, 0.78)
        + 0.20 * _score_linear_100(row.get("support_pressure_spread"), -0.01, 0.10)
        + 0.15 * _score_linear_100(row.get("order_imbalance_ratio"), -0.01, 0.06)
        + 0.15 * _score_linear_100(row.get("cvd_ratio"), -0.01, 0.06),
        2,
    )
    attack_score = round(
        0.20 * _score_linear_100(row.get("return_1d_pct"), 1.0, 9.5)
        + 0.22 * _score_linear_100(row.get("amount_anomaly_20d"), 1.0, 2.8)
        + 0.18 * _score_linear_100(row.get("breakout_vs_prev20_high_pct"), -0.5, 5.0)
        + 0.18 * _score_linear_100(row.get("active_buy_strength"), 0.0, 10.0)
        + 0.12 * _score_linear_100(row.get("l2_main_net_ratio"), 0.0, 0.05)
        + 0.10 * _score_linear_100(row.get("l2_super_net_ratio"), 0.0, 0.03),
        2,
    )
    distribution_score = round(
        0.22 * _score_linear_100(-float(row.get("l2_main_net_ratio") or 0.0), 0.0, 0.05)
        + 0.16 * _score_linear_100(-float(row.get("active_buy_strength") or 0.0), 0.0, 10.0)
        + 0.16 * _score_linear_100(-float(row.get("support_pressure_spread") or 0.0), 0.0, 0.10)
        + 0.14 * _score_linear_100(row.get("cancel_buy_ratio"), 0.03, 0.30)
        + 0.12 * _score_linear_100(row.get("add_sell_ratio"), 0.10, 0.60)
        + 0.10 * _score_linear_100(-float(row.get("order_imbalance_ratio") or 0.0), 0.0, 0.05)
        + 0.10 * _score_linear_100(-float(row.get("cvd_ratio") or 0.0), 0.0, 0.05),
        2,
    )
    washout_score = round(
        0.24 * _score_linear_100(-float(row.get("return_1d_pct") or 0.0), 2.0, 8.0)
        + 0.20 * _score_linear_100(row.get("amount_anomaly_20d"), 1.0, 2.8)
        + 0.20 * _score_linear_100(row.get("l2_main_net_ratio"), -0.01, 0.03)
        + 0.18 * _score_linear_100(row.get("support_pressure_spread"), -0.05, 0.08)
        + 0.18 * _score_linear_100(row.get("cancel_sell_ratio"), 0.03, 0.25),
        2,
    )
    repair_score = round(
        0.28 * _score_linear_100(-float(row.get("prior_3d_min_return_1d_pct") or 0.0), 2.0, 8.0)
        + 0.22 * _score_linear_100(row.get("l2_main_net_amount"), 0.0, max(abs(float(row.get("prior_3d_min_l2_main_net") or 0.0)) * max(params.shakeout_repair_coverage, 1.0), 1.0))
        + 0.18 * _score_linear_100(row.get("active_buy_strength"), 0.0, 8.0)
        + 0.16 * _score_linear_100(row.get("support_pressure_spread"), -0.02, 0.08)
        + 0.16 * _score_linear_100(row.get("amount_anomaly_20d"), 0.9, 2.0),
        2,
    )

    return_1d_pct = float(row.get("return_1d_pct") or 0.0)
    return_20d_pct = float(row.get("return_20d_pct") or 0.0)
    intent_label = "neutral"
    if return_1d_pct <= -4.0:
        if washout_score >= max(params.repair_score_min, distribution_score + 5.0):
            intent_label = "washout"
        elif distribution_score >= params.panic_distribution_score_exit:
            intent_label = "panic_distribution"
        else:
            intent_label = "sharp_drop_unclear"
    elif return_1d_pct >= 4.0:
        if distribution_score >= max(params.distribution_score_warn, attack_score - 5.0) and return_20d_pct >= params.high_return_20d_pct:
            intent_label = "pull_up_distribution"
        elif attack_score >= params.attack_score_min and float(row.get("breakout_vs_prev20_high_pct") or 0.0) >= params.breakout_threshold_pct:
            intent_label = "launch_attack"
        elif attack_score >= params.attack_score_min:
            intent_label = "follow_through_attack"
        else:
            intent_label = "sharp_rise_unclear"
    else:
        if repair_score >= params.repair_score_min:
            intent_label = "shakeout_repair"
        elif accumulation_score >= params.accumulation_score_min and return_20d_pct < params.high_return_20d_pct:
            intent_label = "accumulation"
        elif distribution_score >= params.distribution_score_warn:
            intent_label = "distribution"

    return {
        "intent_label": intent_label,
        "accumulation_score": accumulation_score,
        "attack_score": attack_score,
        "distribution_score": distribution_score,
        "washout_score": washout_score,
        "repair_score": repair_score,
        "entry_signal": intent_label in {"launch_attack", "follow_through_attack", "shakeout_repair"},
        "exit_signal": intent_label in {"panic_distribution", "pull_up_distribution"} or distribution_score >= params.distribution_score_warn,
    }


def _candidate_reasons(row: pd.Series, params: SelectionV2Params) -> tuple[list[str], list[str], list[str]]:
    intent_profile = _compute_intent_profile(row, params)
    types: List[str] = []
    reasons: List[str] = []
    warnings: List[str] = []

    if row["total_amount"] < params.min_amount:
        warnings.append("成交额低于最小观察阈值")
        return types, reasons, warnings

    if intent_profile["accumulation_score"] >= params.accumulation_score_min and row["return_20d_pct"] < params.high_return_20d_pct:
        types.append("accumulation_candidate")
        reasons.append("L2 主力资金近 5 日持续偏强")

    if (
        intent_profile["attack_score"] >= params.attack_score_min
        and
        row["breakout_vs_prev20_high_pct"] >= params.breakout_threshold_pct
        and row["amount_anomaly_20d"] >= params.amount_anomaly_launch
        and row["active_buy_strength"] >= params.active_buy_strength_launch
        and (
            row["l2_main_net_ratio"] >= params.l2_main_net_ratio_launch
            or row["l2_super_net_ratio"] >= params.l2_super_net_ratio_launch
        )
    ):
        types.append("launch_candidate")
        reasons.append("放量突破且主动买强度明显提升")

    if (
        row["return_1d_pct"] >= 7.0
        and intent_profile["attack_score"] >= params.attack_score_min
        and (
            (
                row["amount_anomaly_20d"] >= params.amount_anomaly_event
                and row["trade_count_anomaly_20d"] >= 1.2
            )
            or (
                row["l2_main_net_ratio"] >= params.l2_main_net_ratio_launch * 2.0
                and row["active_buy_strength"] >= params.active_buy_strength_launch * 2.0
            )
        )
    ):
        types.append("event_spike_candidate")
        reasons.append("单日涨幅和成交活跃度异常放大")

    if (
        intent_profile["repair_score"] >= params.repair_score_min
        and row["prior_3d_min_return_1d_pct"] <= params.shakeout_drop_pct
    ):
        types.append("shakeout_repair_candidate")
        reasons.append("急跌后资金回补并出现承接修复")

    if (
        row["return_20d_pct"] >= 10.0
        and row["amount_anomaly_20d"] >= params.second_wave_amount_anomaly
        and row["active_buy_strength"] > 0
        and row["l2_super_net_ratio"] > 0
        and row["max_drawdown_from_20d_high_pct"] >= -12.0
    ):
        types.append("second_wave_candidate")
        reasons.append("前期涨幅后回撤可控且资金重新转强")

    if (
        row["return_20d_pct"] >= params.high_return_20d_pct
        and intent_profile["distribution_score"] >= params.distribution_score_warn
    ):
        types.append("distribution_watch_candidate")
        warnings.append("高位卖压增强，需关注出货风险")

    if row["return_20d_pct"] >= params.high_return_20d_pct:
        warnings.append("20 日涨幅已高，需结合事件层判断持续性")
    if row["active_buy_strength"] < 0:
        warnings.append("主动买强度偏弱")
    if intent_profile["intent_label"] in {"panic_distribution", "pull_up_distribution"}:
        warnings.append("短线意图更接近出货/派发")
    return types, reasons, warnings


def screen_candidates_v2(
    trade_date: str,
    *,
    limit: int = 10,
    params: Optional[SelectionV2Params] = None,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    active_params = params or SelectionV2Params()
    start_date = (pd.Timestamp(trade_date) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    raw_df = load_atomic_daily_window(start_date, trade_date, symbols=symbols, db_path=db_path)
    metrics_df = compute_v2_metrics(raw_df)
    if metrics_df.empty:
        return {
            "trade_date": trade_date,
            "strategy_version": STRATEGY_VERSION_V2,
            "params": asdict(active_params),
            "items": [],
        }
    day_df = metrics_df[metrics_df["trade_date"] == trade_date].copy()
    items: List[Dict[str, Any]] = []
    for _, row in day_df.iterrows():
        intent_profile = _compute_intent_profile(row, active_params)
        candidate_types, reasons, warnings = _candidate_reasons(row, active_params)
        if not candidate_types:
            continue
        entry_allowed, entry_block_reasons = _evaluate_entry_gate(row, intent_profile, active_params)
        funding_score = round(
            100.0 * (
                0.50 * _subscore_linear(row["l2_main_net_ratio"], 0.0, max(active_params.l2_main_net_ratio_launch, 0.04))
                + 0.50 * _subscore_linear(row["l2_super_net_ratio"], 0.0, max(active_params.l2_super_net_ratio_launch, 0.02))
            ),
            2,
        )
        activity_score = round(
            100.0 * (
                0.55 * _subscore_linear(row["amount_anomaly_20d"], 1.0, 2.5)
                + 0.45 * _subscore_linear(row["trade_count_anomaly_20d"], 1.0, 2.0)
            ),
            2,
        )
        structure_score = round(
            100.0 * (
                0.50 * _subscore_linear(row["breakout_vs_prev20_high_pct"], -1.0, 5.0)
                + 0.50 * _subscore_linear(row["active_buy_strength"], 0.0, 10.0)
            ),
            2,
        )
        support_score = round(
            100.0 * (
                0.60 * _subscore_linear(row["support_pressure_spread"], -0.05, 0.10)
                + 0.40 * _subscore_linear(row["positive_l2_bar_ratio"], 0.45, 0.75)
            ),
            2,
        )
        risk_score = round(
            100.0 * (
                0.60 * _subscore_linear(row["return_20d_pct"], 10.0, 50.0)
                + 0.40 * _subscore_linear(-row["support_pressure_spread"], 0.0, 0.08)
            ),
            2,
        )
        quant_score = round(
            0.30 * funding_score + 0.25 * activity_score + 0.25 * structure_score + 0.20 * support_score - 0.10 * risk_score,
            2,
        )
        items.append(
            {
                "symbol": str(row["symbol"]),
                "trade_date": str(row["trade_date"]),
                "candidate_types": candidate_types,
                "quant_score": quant_score,
                "funding_score": funding_score,
                "activity_score": activity_score,
                "structure_score": structure_score,
                "support_score": support_score,
                "risk_score": risk_score,
                "top_reasons": reasons[:3],
                "warnings": warnings[:3],
                "intent_profile": intent_profile,
                "entry_allowed": entry_allowed,
                "entry_block_reasons": entry_block_reasons[:3],
                "metrics": {
                    "close": float(row["close"]),
                    "total_amount": float(row["total_amount"]),
                    "return_1d_pct": float(row["return_1d_pct"] or 0.0),
                    "return_5d_pct": float(row["return_5d_pct"] or 0.0),
                    "return_20d_pct": float(row["return_20d_pct"] or 0.0),
                    "amount_anomaly_20d": float(row["amount_anomaly_20d"] or 0.0),
                    "active_buy_strength": float(row["active_buy_strength"] or 0.0),
                    "l2_main_net_ratio": float(row["l2_main_net_ratio"] or 0.0),
                    "l2_super_net_ratio": float(row["l2_super_net_ratio"] or 0.0),
                    "support_pressure_spread": float(row["support_pressure_spread"] or 0.0),
                    "breakout_vs_prev20_high_pct": float(row["breakout_vs_prev20_high_pct"] or 0.0),
                    "order_imbalance_ratio": float(row["order_imbalance_ratio"] or 0.0),
                    "cvd_ratio": float(row["cvd_ratio"] or 0.0),
                    "add_buy_ratio": float(row["add_buy_ratio"] or 0.0),
                    "add_sell_ratio": float(row["add_sell_ratio"] or 0.0),
                    "cancel_buy_ratio": float(row["cancel_buy_ratio"] or 0.0),
                    "cancel_sell_ratio": float(row["cancel_sell_ratio"] or 0.0),
                },
            }
        )
    items = sorted(items, key=lambda item: (-item["quant_score"], item["symbol"]))[: int(limit)]
    return {
        "trade_date": trade_date,
        "strategy_version": STRATEGY_VERSION_V2,
        "params": asdict(active_params),
        "items": items,
    }


def _is_limit_up_day(row: pd.Series, params: SelectionV2Params) -> bool:
    prev_close = float(row.get("prev_close") or 0.0)
    if prev_close <= 0:
        return False
    limit_price = prev_close * (1.0 + float(params.limit_up_pct) / 100.0)
    day_range_ratio = abs(float(row.get("high") or 0.0) - float(row.get("low") or 0.0)) / prev_close
    locked = float(row.get("open") or 0.0) >= limit_price * 0.995 and float(row.get("low") or 0.0) >= limit_price * 0.995
    return float(row.get("return_1d_pct") or 0.0) >= float(params.limit_up_pct) and locked and day_range_ratio <= 0.002


def _is_limit_down_day(row: pd.Series, params: SelectionV2Params) -> bool:
    prev_close = float(row.get("prev_close") or 0.0)
    if prev_close <= 0:
        return False
    limit_price = prev_close * (1.0 + float(params.limit_down_pct) / 100.0)
    day_range_ratio = abs(float(row.get("high") or 0.0) - float(row.get("low") or 0.0)) / prev_close
    locked = float(row.get("open") or 0.0) <= limit_price * 1.005 and float(row.get("high") or 0.0) <= limit_price * 1.005
    return float(row.get("return_1d_pct") or 0.0) <= float(params.limit_down_pct) and locked and day_range_ratio <= 0.002


def _apply_buy_costs(price: float, params: SelectionV2Params) -> float:
    slip = float(params.buy_slippage_bp) / 10_000.0
    fee = (float(params.round_trip_fee_bp) / 10_000.0) / 2.0
    return float(price) * (1.0 + slip + fee)


def _apply_sell_costs(price: float, params: SelectionV2Params) -> float:
    slip = float(params.sell_slippage_bp) / 10_000.0
    fee = (float(params.round_trip_fee_bp) / 10_000.0) / 2.0
    return float(price) * (1.0 - slip - fee)


def _evaluate_entry_gate(row: pd.Series, intent_profile: Dict[str, Any], params: SelectionV2Params) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    return_20d_pct = float(row.get("return_20d_pct") or 0.0)
    cvd_ratio = float(row.get("cvd_ratio") or 0.0)
    if return_20d_pct > float(params.entry_return_20d_cap):
        reasons.append("20日涨幅过热，禁止继续追击")
    if intent_profile["intent_label"] in {"launch_attack", "follow_through_attack"} and cvd_ratio < float(params.entry_attack_cvd_floor):
        reasons.append("攻击型信号但 CVD 偏弱，疑似拉高分歧")
    return len(reasons) == 0, reasons


def replay_symbol_v2(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    params: Optional[SelectionV2Params] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = params or SelectionV2Params()
    lookback_start = (pd.Timestamp(start_date) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    raw_df = load_atomic_daily_window(lookback_start, end_date, symbols=[symbol], db_path=db_path)
    metrics_df = compute_v2_metrics(raw_df)
    metrics_df = metrics_df[metrics_df["trade_date"] >= start_date].copy()
    if metrics_df.empty:
        return {
            "symbol": symbol.lower(),
            "strategy_version": STRATEGY_VERSION_V2,
            "params": asdict(active_params),
            "daily_states": [],
            "trades": [],
        }

    daily_states: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    pending_entry: Optional[str] = None
    pending_exit: Optional[Dict[str, Any]] = None
    position: Optional[Dict[str, Any]] = None
    distribution_streak = 0

    for _, row in metrics_df.iterrows():
        intent_profile = _compute_intent_profile(row, active_params)
        candidate_types, reasons, warnings = _candidate_reasons(row, active_params)
        derived_state = "watch"
        if intent_profile["intent_label"] in {"panic_distribution", "pull_up_distribution", "distribution"}:
            derived_state = "distribution_warning"
        elif intent_profile["intent_label"] in {"launch_attack", "follow_through_attack"}:
            derived_state = "launching"
        elif intent_profile["intent_label"] == "shakeout_repair":
            derived_state = "shakeout_repair"
        elif intent_profile["intent_label"] in {"event_spike", "sharp_rise_unclear"} or "event_spike_candidate" in candidate_types:
            derived_state = "event_spike"
        elif intent_profile["intent_label"] == "washout":
            derived_state = "shakeout"
        elif intent_profile["intent_label"] == "accumulation":
            derived_state = "accumulating"

        exit_reason: Optional[str] = None
        state_for_day = derived_state
        entry_allowed, entry_block_reasons = _evaluate_entry_gate(row, intent_profile, active_params)

        if pending_exit is not None and position is not None:
            if _is_limit_down_day(row, active_params):
                state_for_day = "exit_blocked_limit_down"
            else:
                gross_exit_price = float(row["open"])
                exit_price = _apply_sell_costs(gross_exit_price, active_params)
                gross_return_pct = ((gross_exit_price / float(position["gross_entry_price"])) - 1.0) * 100.0
                net_return_pct = ((exit_price / float(position["entry_price"])) - 1.0) * 100.0
                trades.append(
                    {
                        "symbol": symbol.lower(),
                        "signal_date": str(position["signal_date"]),
                        "entry_date": str(position["entry_date"]),
                        "entry_price": round(float(position["entry_price"]), 4),
                        "gross_entry_price": round(float(position["gross_entry_price"]), 4),
                        "exit_signal_date": str(pending_exit["signal_date"]),
                        "exit_date": str(row["trade_date"]),
                        "exit_price": round(exit_price, 4),
                        "gross_exit_price": round(gross_exit_price, 4),
                        "return_pct": round(gross_return_pct, 2),
                        "net_return_pct": round(net_return_pct, 2),
                        "max_runup_pct": round(float(position["max_runup_pct"]), 2),
                        "max_drawdown_pct": round(float(position["max_drawdown_pct"]), 2),
                        "holding_days": int(position["holding_days"]),
                        "exit_reason": str(pending_exit["reason"]),
                    }
                )
                position = None
                pending_exit = None
                distribution_streak = 0
                state_for_day = "exit"
        elif pending_entry is not None and position is None:
            if _is_limit_up_day(row, active_params):
                pending_entry = None
                state_for_day = "entry_blocked_limit_up"
            else:
                gross_entry_price = float(row["open"])
                entry_price = _apply_buy_costs(gross_entry_price, active_params)
                position = {
                    "signal_date": pending_entry,
                    "entry_date": str(row["trade_date"]),
                    "entry_price": entry_price,
                    "gross_entry_price": gross_entry_price,
                    "max_runup_pct": ((float(row["high"]) / gross_entry_price) - 1.0) * 100.0,
                    "max_drawdown_pct": ((float(row["low"]) / gross_entry_price) - 1.0) * 100.0,
                    "holding_days": 1,
                }
                pending_entry = None
                distribution_streak = 0
                state_for_day = "entered"
        elif position is not None:
            position["holding_days"] += 1
            position["max_runup_pct"] = max(
                float(position["max_runup_pct"]),
                ((float(row["high"]) / float(position["gross_entry_price"])) - 1.0) * 100.0,
            )
            position["max_drawdown_pct"] = min(
                float(position["max_drawdown_pct"]),
                ((float(row["low"]) / float(position["gross_entry_price"])) - 1.0) * 100.0,
            )
            stop_loss_hit = ((float(row["close"]) / float(position["gross_entry_price"])) - 1.0) * 100.0 <= active_params.stop_loss_pct
            if derived_state == "distribution_warning":
                distribution_streak += 1
            else:
                distribution_streak = 0
            state_for_day = "holding" if distribution_streak == 0 else "distribution_warning"
            if stop_loss_hit:
                exit_reason = "stop_loss"
            elif intent_profile["intent_label"] in {"panic_distribution", "pull_up_distribution"} and intent_profile["distribution_score"] >= active_params.panic_distribution_score_exit:
                exit_reason = "panic_distribution_exit"
            elif distribution_streak >= active_params.distribution_confirm_days:
                exit_reason = "distribution_warning_confirmed"
            elif int(position["holding_days"]) >= active_params.max_holding_days:
                exit_reason = "max_holding_days"
            if exit_reason and pending_exit is None:
                pending_exit = {
                    "signal_date": str(row["trade_date"]),
                    "reason": exit_reason,
                }
                state_for_day = "exit_signal"
        elif intent_profile["entry_signal"] or derived_state in {"launching", "event_spike", "shakeout_repair"}:
            if entry_allowed:
                pending_entry = str(row["trade_date"])
                state_for_day = "entry_signal"
            else:
                state_for_day = "watch"
                warnings = [*warnings, *entry_block_reasons][:3]

        daily_states.append(
            {
                "date": str(row["trade_date"]),
                "state": state_for_day,
                "candidate_types": candidate_types,
                "top_reasons": reasons[:3],
                "warnings": warnings[:3],
                "intent_label": intent_profile["intent_label"],
                "accumulation_score": round(float(intent_profile["accumulation_score"]), 2),
                "attack_score": round(float(intent_profile["attack_score"]), 2),
                "distribution_score": round(float(intent_profile["distribution_score"]), 2),
                "washout_score": round(float(intent_profile["washout_score"]), 2),
                "repair_score": round(float(intent_profile["repair_score"]), 2),
                "close": round(float(row["close"]), 4),
                "return_1d_pct": round(float(row["return_1d_pct"] or 0.0), 2),
                "return_20d_pct": round(float(row["return_20d_pct"] or 0.0), 2),
                "amount_anomaly_20d": round(float(row["amount_anomaly_20d"] or 0.0), 4),
                "active_buy_strength": round(float(row["active_buy_strength"] or 0.0), 4),
                "l2_main_net_ratio": round(float(row["l2_main_net_ratio"] or 0.0), 6),
                "support_pressure_spread": round(float(row["support_pressure_spread"] or 0.0), 6),
                "order_imbalance_ratio": round(float(row["order_imbalance_ratio"] or 0.0), 6),
                "cvd_ratio": round(float(row["cvd_ratio"] or 0.0), 6),
                "add_buy_ratio": round(float(row["add_buy_ratio"] or 0.0), 6),
                "add_sell_ratio": round(float(row["add_sell_ratio"] or 0.0), 6),
                "cancel_buy_ratio": round(float(row["cancel_buy_ratio"] or 0.0), 6),
                "cancel_sell_ratio": round(float(row["cancel_sell_ratio"] or 0.0), 6),
                "entry_allowed": entry_allowed,
                "entry_block_reasons": entry_block_reasons[:3],
                "pending_entry_signal_date": pending_entry,
                "pending_exit_signal_date": None if pending_exit is None else str(pending_exit["signal_date"]),
            }
        )

    if position is not None and not metrics_df.empty:
        last_row = metrics_df.iloc[-1]
        gross_exit_price = float(last_row["close"])
        exit_price = _apply_sell_costs(gross_exit_price, active_params)
        gross_return_pct = ((gross_exit_price / float(position["gross_entry_price"])) - 1.0) * 100.0
        net_return_pct = ((exit_price / float(position["entry_price"])) - 1.0) * 100.0
        trades.append(
            {
                "symbol": symbol.lower(),
                "signal_date": str(position["signal_date"]),
                "entry_date": str(position["entry_date"]),
                "entry_price": round(float(position["entry_price"]), 4),
                "gross_entry_price": round(float(position["gross_entry_price"]), 4),
                "exit_signal_date": str(pending_exit["signal_date"]) if pending_exit is not None else str(last_row["trade_date"]),
                "exit_date": str(last_row["trade_date"]),
                "exit_price": round(exit_price, 4),
                "gross_exit_price": round(gross_exit_price, 4),
                "return_pct": round(gross_return_pct, 2),
                "net_return_pct": round(net_return_pct, 2),
                "max_runup_pct": round(float(position["max_runup_pct"]), 2),
                "max_drawdown_pct": round(float(position["max_drawdown_pct"]), 2),
                "holding_days": int(position["holding_days"]),
                "exit_reason": str(pending_exit["reason"]) if pending_exit is not None else "window_end",
                "window_forced_exit": pending_exit is not None,
            }
        )

    return {
        "symbol": symbol.lower(),
        "strategy_version": STRATEGY_VERSION_V2,
        "params": asdict(active_params),
        "daily_states": daily_states,
        "trades": trades,
    }


def _load_company_basics(
    symbol: str,
    trade_date: str,
    *,
    main_db_path: Optional[str] = None,
    user_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_symbol = symbol.lower()
    basics: Dict[str, Any] = {
        "symbol": normalized_symbol,
        "name": None,
        "market_cap": None,
        "source": None,
        "market_cap_missing": True,
        "company_context_missing": True,
    }
    with _main_connection(main_db_path) as conn:
        row = conn.execute(
            """
            SELECT symbol, name, market_cap, as_of_date, source
            FROM stock_universe_meta
            WHERE lower(symbol)=lower(?) AND as_of_date <= ?
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            (normalized_symbol, trade_date),
        ).fetchone()
        if row:
            basics.update(
                {
                    "name": str(row["name"]),
                    "market_cap": float(row["market_cap"]) if row["market_cap"] is not None else None,
                    "source": str(row["source"] or "stock_universe_meta"),
                    "market_cap_missing": row["market_cap"] is None,
                    "company_context_missing": False,
                }
            )
    resolved_user_db = user_db_path or resolve_selection_v2_user_db_path()
    if basics["name"] is None and resolved_user_db and os.path.exists(resolved_user_db):
        conn = sqlite3.connect(resolved_user_db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT symbol, name FROM watchlist WHERE lower(symbol)=lower(?) LIMIT 1",
                (normalized_symbol,),
            ).fetchone()
            if row:
                basics.update(
                    {
                        "name": str(row["name"]),
                        "source": "watchlist",
                        "company_context_missing": False,
                    }
                )
        finally:
            conn.close()
    if basics["name"] is None:
        basics["name"] = normalized_symbol
    return basics


def _derive_theme_tags(texts: Sequence[str]) -> List[str]:
    joined = " ".join(str(text or "").lower() for text in texts)
    tags: List[str] = []
    for tag, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in joined for keyword in keywords):
            tags.append(tag)
    return tags


def _load_event_timeline(
    symbol: str,
    trade_date: str,
    *,
    limit: int = 12,
    main_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_symbol = symbol.lower()
    cutoff = f"{trade_date} 23:59:59"
    timeline: List[Dict[str, Any]] = []
    official_count = 0
    sentiment_count = 0
    with _main_connection(main_db_path) as conn:
        try:
            rows = conn.execute(
                """
                SELECT source, source_type, event_subtype, title, content_text, published_at, importance, is_official
                FROM stock_events
                WHERE lower(symbol)=lower(?) AND published_at <= ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (normalized_symbol, cutoff, int(limit)),
            ).fetchall()
            for row in rows:
                official_count += int(row["is_official"] or 0)
                timeline.append(
                    {
                        "kind": "stock_event",
                        "time": str(row["published_at"] or ""),
                        "source": str(row["source"] or ""),
                        "source_type": str(row["source_type"] or ""),
                        "event_subtype": str(row["event_subtype"] or ""),
                        "title": str(row["title"] or ""),
                        "content": str(row["content_text"] or "")[:180],
                        "importance": int(row["importance"] or 0),
                        "is_official": bool(row["is_official"] or 0),
                    }
                )
        except sqlite3.OperationalError:
            pass
        try:
            rows = conn.execute(
                """
                SELECT source, event_type, content, pub_time, reply_count, like_count
                FROM sentiment_events
                WHERE lower(symbol)=lower(?) AND pub_time <= ?
                ORDER BY pub_time DESC
                LIMIT ?
                """,
                (normalized_symbol, cutoff, int(limit)),
            ).fetchall()
            for row in rows:
                sentiment_count += 1
                timeline.append(
                    {
                        "kind": "sentiment_event",
                        "time": str(row["pub_time"] or ""),
                        "source": str(row["source"] or ""),
                        "source_type": str(row["event_type"] or ""),
                        "event_subtype": "",
                        "title": str(row["content"] or "")[:60],
                        "content": str(row["content"] or "")[:180],
                        "importance": 0,
                        "is_official": False,
                        "engagement": {
                            "reply_count": int(row["reply_count"] or 0),
                            "like_count": int(row["like_count"] or 0),
                        },
                    }
                )
        except sqlite3.OperationalError:
            pass
    timeline = sorted(timeline, key=lambda item: str(item.get("time") or ""), reverse=True)[:limit]
    texts = [str(item.get("title") or "") for item in timeline] + [str(item.get("content") or "") for item in timeline]
    return {
        "items": timeline,
        "event_context_missing": len(timeline) == 0,
        "official_event_count": official_count,
        "sentiment_event_count": sentiment_count,
        "theme_tags": _derive_theme_tags(texts),
    }


def _load_sentiment_snapshot(
    symbol: str,
    trade_date: str,
    *,
    main_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "available": False,
        "trade_date": None,
        "sample_count": 0,
        "sentiment_score": None,
        "direction_label": None,
        "consensus_strength": None,
        "emotion_temperature": None,
        "risk_tag": None,
        "summary_text": None,
    }
    with _main_connection(main_db_path) as conn:
        try:
            row = conn.execute(
                """
                SELECT trade_date, sample_count, sentiment_score, direction_label,
                       consensus_strength, emotion_temperature, risk_tag, summary_text
                FROM sentiment_daily_scores
                WHERE lower(symbol)=lower(?) AND trade_date <= ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (symbol.lower(), trade_date),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
    if row:
        snapshot.update(
            {
                "available": True,
                "trade_date": str(row["trade_date"] or ""),
                "sample_count": int(row["sample_count"] or 0),
                "sentiment_score": float(row["sentiment_score"]) if row["sentiment_score"] is not None else None,
                "direction_label": str(row["direction_label"] or ""),
                "consensus_strength": int(row["consensus_strength"] or 0),
                "emotion_temperature": int(row["emotion_temperature"] or 0),
                "risk_tag": str(row["risk_tag"] or ""),
                "summary_text": str(row["summary_text"] or ""),
            }
        )
    return snapshot


def build_research_card_v2(
    symbol: str,
    trade_date: str,
    candidate: Dict[str, Any],
    *,
    main_db_path: Optional[str] = None,
    user_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    basics = _load_company_basics(
        symbol,
        trade_date,
        main_db_path=main_db_path,
        user_db_path=user_db_path,
    )
    events = _load_event_timeline(symbol, trade_date, main_db_path=main_db_path)
    sentiment = _load_sentiment_snapshot(symbol, trade_date, main_db_path=main_db_path)
    consistency = "unknown"
    if events["official_event_count"] > 0 and candidate["candidate_types"]:
        consistency = "confirmed"
    elif events["event_context_missing"]:
        consistency = "unknown"
    elif candidate["candidate_types"]:
        consistency = "funds_only"
    event_strength = "weak"
    if events["official_event_count"] > 0:
        event_strength = "strong"
    elif sentiment["available"] and sentiment["sample_count"] >= 10 and abs(float(sentiment["sentiment_score"] or 0.0)) >= 30:
        event_strength = "medium"
    elif not events["event_context_missing"]:
        event_strength = "medium"
    event_duration = "short_term"
    if any(tag in {"算力", "AI", "业绩", "订单", "政策"} for tag in events["theme_tags"]):
        event_duration = "medium_term"
    if "event_spike_candidate" in candidate["candidate_types"] and not events["theme_tags"]:
        event_duration = "short_term"
    profile_bits = [basics["name"]]
    if events["theme_tags"]:
        profile_bits.append(" / ".join(events["theme_tags"][:3]))
    if "event_spike_candidate" in candidate["candidate_types"]:
        profile_bits.append("事件驱动候选")
    elif "launch_candidate" in candidate["candidate_types"]:
        profile_bits.append("启动候选")
    elif "shakeout_repair_candidate" in candidate["candidate_types"]:
        profile_bits.append("洗盘修复候选")
    company_profile = " | ".join(profile_bits)
    business_summary = basics["name"]
    if events["theme_tags"]:
        business_summary = f"{basics['name']} 当前市场关注主题：{' / '.join(events['theme_tags'][:3])}"
    core_thesis = ""
    if events["theme_tags"]:
        core_thesis = f"{' / '.join(events['theme_tags'][:2])} 相关叙事与 L2 资金动作开始共振"
    elif candidate["top_reasons"]:
        core_thesis = candidate["top_reasons"][0]
    action_hint = "observe_only"
    if not events["event_context_missing"] and candidate["candidate_types"]:
        action_hint = "review_for_entry"
    if sentiment["available"] and sentiment["direction_label"] == "偏空":
        action_hint = "review_with_caution"
    return {
        "symbol": symbol.lower(),
        "trade_date": trade_date,
        "name": basics["name"],
        "market_cap": basics["market_cap"],
        "market_cap_missing": basics["market_cap_missing"],
        "company_context_missing": basics["company_context_missing"],
        "event_context_missing": events["event_context_missing"],
        "company_profile": company_profile,
        "business_summary": business_summary,
        "core_thesis": core_thesis,
        "event_strength": event_strength,
        "event_duration": event_duration,
        "theme_tags": events["theme_tags"],
        "fundamental_funding_consistency": consistency,
        "action_hint": action_hint,
        "llm_action_hint": action_hint,
        "sentiment_snapshot": sentiment,
        "valuation_elasticity": {
            "has_estimate": False,
            "key_assumptions": [],
            "rough_market_cap_range": None,
            "uncertainty": "需要后续接入公司研究/LLM 层补全",
        },
        "tracking_points": candidate["top_reasons"][:2],
        "risk_points": candidate["warnings"][:2],
        "event_timeline": events["items"],
    }


def _resolve_replay_end_date(trade_date: str, replay_end_date: Optional[str], params: SelectionV2Params) -> str:
    if replay_end_date:
        return replay_end_date
    return (pd.Timestamp(trade_date) + pd.Timedelta(days=max(int(params.max_holding_days) * 3, 90))).strftime("%Y-%m-%d")


def _infer_lifecycle_phase(candidate_types: Sequence[str], intent_profile: Dict[str, Any]) -> tuple[str, str, float]:
    candidate_set = {str(item) for item in candidate_types}
    intent_label = str(intent_profile.get("intent_label") or "")
    if "launch_candidate" in candidate_set:
        return "launch", "启动", 100.0
    if "shakeout_repair_candidate" in candidate_set:
        return "repair", "洗盘修复", 93.0
    if "second_wave_candidate" in candidate_set:
        return "second_wave", "二波", 88.0
    if "event_spike_candidate" in candidate_set:
        return "event", "事件驱动", 84.0
    if "accumulation_candidate" in candidate_set:
        return "accumulation", "吸筹", 76.0
    if "distribution_watch_candidate" in candidate_set:
        return "distribution_watch", "出货预警", 28.0
    if intent_label in {"launch_attack", "follow_through_attack"}:
        return "launch", "启动", 96.0
    if intent_label == "shakeout_repair":
        return "repair", "洗盘修复", 90.0
    if intent_label == "accumulation":
        return "accumulation", "吸筹", 72.0
    if intent_label in {"panic_distribution", "pull_up_distribution", "distribution"}:
        return "distribution_watch", "出货预警", 24.0
    return "observe", "观察", 52.0


def _compute_live_rank_score(item: Dict[str, Any], params: SelectionV2Params) -> tuple[float, str, str, str]:
    intent_profile = item.get("intent_profile") or {}
    candidate_types = item.get("candidate_types") or []
    candidate_set = {str(entry) for entry in candidate_types}
    phase_code, phase_label, phase_score = _infer_lifecycle_phase(candidate_types, intent_profile)
    quant_score = float(item.get("quant_score") or 0.0)
    funding_score = float(item.get("funding_score") or 0.0)
    structure_score = float(item.get("structure_score") or 0.0)
    support_score = float(item.get("support_score") or 0.0)
    accumulation_score = float(intent_profile.get("accumulation_score") or 0.0)
    attack_score = float(intent_profile.get("attack_score") or 0.0)
    distribution_score = float(intent_profile.get("distribution_score") or 0.0)
    repair_score = float(intent_profile.get("repair_score") or 0.0)
    return_20d_pct = float(item.get("metrics", {}).get("return_20d_pct") or 0.0)
    entry_allowed = bool(item.get("entry_allowed", True))
    combo_bonus = 0.0
    if {"launch_candidate", "second_wave_candidate"}.issubset(candidate_set):
        combo_bonus += 12.0
    if {"accumulation_candidate", "shakeout_repair_candidate"}.issubset(candidate_set):
        combo_bonus += 14.0
    if {"accumulation_candidate", "launch_candidate"}.issubset(candidate_set):
        combo_bonus += 8.0
    if {"shakeout_repair_candidate", "second_wave_candidate"}.issubset(candidate_set):
        combo_bonus += 6.0
    if len(candidate_set) >= 2:
        combo_bonus += 4.0

    score = (
        0.12 * phase_score
        + 0.15 * quant_score
        + 0.16 * attack_score
        + 0.12 * repair_score
        + 0.10 * accumulation_score
        + 0.08 * funding_score
        + 0.05 * structure_score
        + 0.04 * support_score
        + 0.06 * min(max(return_20d_pct, 0.0), float(params.high_return_20d_pct))
        - 0.08 * distribution_score
        + combo_bonus
    )
    if not entry_allowed:
        score -= 12.0
    if return_20d_pct > float(params.entry_return_20d_cap):
        score -= 10.0
    elif return_20d_pct > float(params.high_return_20d_pct):
        score -= 4.0
    live_rank_score = round(max(0.0, min(100.0, score)), 2)

    if not entry_allowed:
        action_label = "拦截"
    elif phase_code in {"launch", "repair", "second_wave", "event"}:
        action_label = "进场"
    elif phase_code == "accumulation":
        action_label = "观察"
    elif phase_code == "distribution_watch":
        action_label = "回避"
    else:
        action_label = "跟踪"
    return live_rank_score, phase_code, phase_label, action_label


def replay_trade_date_v2(
    trade_date: str,
    *,
    limit: int = 10,
    params: Optional[SelectionV2Params] = None,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    replay_end_date: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = params or SelectionV2Params()
    candidates_payload = screen_candidates_v2(
        trade_date=trade_date,
        limit=limit,
        params=active_params,
        db_path=db_path,
        symbols=symbols,
    )
    resolved_end_date = _resolve_replay_end_date(trade_date, replay_end_date, active_params)
    trade_results: List[Dict[str, Any]] = []
    for item in candidates_payload["items"]:
        research = build_research_card_v2(
            item["symbol"],
            trade_date,
            item,
            main_db_path=None,
            user_db_path=None,
        )
        replay_payload = replay_symbol_v2(
            symbol=item["symbol"],
            start_date=trade_date,
            end_date=resolved_end_date,
            params=active_params,
            db_path=db_path,
        )
        matching_trade = next(
            (trade for trade in replay_payload["trades"] if str(trade["signal_date"]) == trade_date),
            None,
        )
        trade_results.append(
            {
                "symbol": item["symbol"],
                "candidate_types": item["candidate_types"],
                "quant_score": item["quant_score"],
                "top_reasons": item["top_reasons"],
                "warnings": item["warnings"],
                "intent_profile": item.get("intent_profile", {}),
                "entry_allowed": item.get("entry_allowed", True),
                "entry_block_reasons": item.get("entry_block_reasons", []),
                "research": research,
                "trade": matching_trade,
                "daily_state_count": len(replay_payload["daily_states"]),
            }
        )
    return {
        "trade_date": trade_date,
        "replay_end_date": resolved_end_date,
        "strategy_version": STRATEGY_VERSION_V2,
        "params": asdict(active_params),
        "candidates": trade_results,
    }


def _summarize_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "avg_gross_return_pct": 0.0,
            "median_return_pct": 0.0,
            "max_return_pct": 0.0,
            "min_return_pct": 0.0,
            "avg_win_return_pct": 0.0,
            "avg_loss_return_pct": 0.0,
            "avg_holding_days": 0.0,
            "total_return_pct": 0.0,
            "compounded_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }
    returns = pd.Series([float(trade.get("net_return_pct", trade["return_pct"])) for trade in trades])
    gross_returns = pd.Series([float(trade["return_pct"]) for trade in trades])
    holding_days = pd.Series([int(trade["holding_days"]) for trade in trades])
    win_returns = returns[returns > 0]
    loss_returns = returns[returns <= 0]
    equity = (1.0 + (returns / 100.0)).cumprod()
    rolling_peak = equity.cummax()
    drawdown = (equity / rolling_peak) - 1.0
    return {
        "trade_count": int(len(trades)),
        "win_rate": round(float((returns > 0).mean() * 100.0), 2),
        "avg_return_pct": round(float(returns.mean()), 2),
        "avg_gross_return_pct": round(float(gross_returns.mean()), 2),
        "median_return_pct": round(float(returns.median()), 2),
        "max_return_pct": round(float(returns.max()), 2),
        "min_return_pct": round(float(returns.min()), 2),
        "avg_win_return_pct": round(float(win_returns.mean()), 2) if not win_returns.empty else 0.0,
        "avg_loss_return_pct": round(float(loss_returns.mean()), 2) if not loss_returns.empty else 0.0,
        "avg_holding_days": round(float(holding_days.mean()), 2),
        "total_return_pct": round(float(returns.sum()), 2),
        "compounded_return_pct": round(float((equity.iloc[-1] - 1.0) * 100.0), 2),
        "max_drawdown_pct": round(float(drawdown.min() * 100.0), 2),
    }


def backtest_range_v2(
    start_date: str,
    end_date: str,
    *,
    limit: int = 10,
    params: Optional[SelectionV2Params] = None,
    db_path: Optional[str] = None,
    symbols: Optional[Sequence[str]] = None,
    replay_end_date: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = params or SelectionV2Params()
    resolved_replay_end = _resolve_replay_end_date(end_date, replay_end_date, active_params)
    trading_days = pd.bdate_range(start_date, end_date).strftime("%Y-%m-%d").tolist()
    daily_results: List[Dict[str, Any]] = []
    accepted_trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    last_exit_by_symbol: Dict[str, str] = {}
    max_open_positions = max(1, int(active_params.max_open_positions))
    max_new_positions_per_day = max(1, int(active_params.max_new_positions_per_day))

    def _open_positions_on(entry_date: str) -> int:
        return sum(1 for trade in accepted_trades if str(trade["entry_date"]) <= entry_date < str(trade["exit_date"]))

    def _new_positions_on(entry_date: str) -> int:
        return sum(1 for trade in accepted_trades if str(trade["entry_date"]) == entry_date)

    for trade_date in trading_days:
        daily_payload = replay_trade_date_v2(
            trade_date=trade_date,
            limit=limit,
            params=active_params,
            db_path=db_path,
            symbols=symbols,
            replay_end_date=resolved_replay_end,
        )
        accepted_for_day = 0
        skipped_position_limit = 0
        skipped_symbol_conflict = 0
        for candidate in daily_payload["candidates"]:
            trade = candidate.get("trade")
            if not trade:
                continue
            symbol = str(trade["symbol"])
            last_exit = last_exit_by_symbol.get(symbol)
            if last_exit and str(trade["entry_date"]) <= last_exit:
                skipped_symbol_conflict += 1
                continue
            if _open_positions_on(str(trade["entry_date"])) >= max_open_positions:
                skipped_position_limit += 1
                continue
            if _new_positions_on(str(trade["entry_date"])) >= max_new_positions_per_day:
                skipped_position_limit += 1
                continue
            accepted_trade = {
                **trade,
                "quant_score": candidate.get("quant_score"),
                "candidate_types": candidate.get("candidate_types", []),
            }
            accepted_trades.append(accepted_trade)
            last_exit_by_symbol[symbol] = str(trade["exit_date"])
            accepted_for_day += 1
        daily_results.append(
            {
                "trade_date": trade_date,
                "candidate_count": len(daily_payload["candidates"]),
                "trade_count": accepted_for_day,
                "skipped_position_limit": skipped_position_limit,
                "skipped_symbol_conflict": skipped_symbol_conflict,
            }
        )
    nav = 1.0
    for trade in sorted(accepted_trades, key=lambda item: (str(item["exit_date"]), str(item["entry_date"]), str(item["symbol"]))):
        nav *= 1.0 + (float(trade.get("net_return_pct", trade["return_pct"])) / 100.0)
        equity_curve.append(
            {
                "date": str(trade["exit_date"]),
                "symbol": str(trade["symbol"]),
                "nav": round(nav, 6),
            }
        )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "replay_end_date": resolved_replay_end,
        "strategy_version": STRATEGY_VERSION_V2,
        "params": asdict(active_params),
        "summary": _summarize_trades(accepted_trades),
        "daily_results": daily_results,
        "equity_curve": equity_curve,
        "trades": accepted_trades,
    }


def get_selection_v2_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    with _atomic_connection() as conn:
        row = conn.execute("SELECT MIN(trade_date), MAX(trade_date) FROM atomic_trade_daily").fetchone()
        min_date = str(row[0]) if row and row[0] else None
        max_date = str(row[1]) if row and row[1] else None
        resolved_start = start_date or min_date
        resolved_end = end_date or max_date
        if not resolved_start or not resolved_end:
            return {"start_date": resolved_start, "end_date": resolved_end, "strategy": STRATEGY_VERSION_V2, "items": []}
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (resolved_start, resolved_end),
        ).fetchall()
    available_dates = {str(item[0]) for item in rows}
    days = pd.date_range(resolved_start, resolved_end, freq="D").strftime("%Y-%m-%d").tolist()
    items: List[Dict[str, Any]] = []
    for day in days:
        is_trade_day = bool(day in available_dates)
        items.append(
            {
                "date": day,
                "is_trade_day": is_trade_day,
                "signal_count": 0,
                "selectable": is_trade_day,
                "disabled_reason": None if is_trade_day else "休市/无原始数据",
            }
        )
    return {
        "start_date": resolved_start,
        "end_date": resolved_end,
        "strategy": "v2",
        "items": items,
    }


def get_candidates_v2_api(trade_date: Optional[str], limit: int = 10, replay_validation: bool = False) -> Dict[str, Any]:
    active_params = build_selection_v2_page_params()
    target_date = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
    output_limit = max(1, int(limit))
    screen_limit = max(output_limit, 120)
    payload = screen_candidates_v2(
        target_date,
        limit=screen_limit,
        params=active_params,
    )
    replay_by_symbol: Dict[str, Dict[str, Any]] = {}
    if replay_validation and payload["items"]:
        replay_end_date = min(
            (pd.Timestamp(target_date) + pd.Timedelta(days=120)).strftime("%Y-%m-%d"),
            pd.Timestamp.today().strftime("%Y-%m-%d"),
        )
        replay_payload = replay_trade_date_v2(
            target_date,
            limit=len(payload["items"]),
            params=active_params,
            replay_end_date=replay_end_date,
        )
        replay_by_symbol = {str(item["symbol"]).lower(): item for item in replay_payload.get("candidates", [])}
    items: List[Dict[str, Any]] = []
    for item in payload["items"]:
        replay_item = replay_by_symbol.get(str(item["symbol"]).lower(), {})
        trade = replay_item.get("trade") or {}
        replay_return_pct = trade.get("net_return_pct")
        live_rank_score, lifecycle_phase, lifecycle_phase_label, action_label = _compute_live_rank_score(item, active_params)
        replay_rank_score = float(replay_return_pct) if replay_return_pct is not None else None
        items.append(
            {
                "rank": 0,
                "symbol": item["symbol"],
                "name": item["symbol"],
                "trade_date": item["trade_date"],
                "score": live_rank_score,
                "signal": 1 if item.get("entry_allowed", True) else 0,
                "signal_label": "v2_entry_candidate" if item.get("entry_allowed", True) else "v2_blocked_candidate",
                "current_judgement": "可观察/候选" if item.get("entry_allowed", True) else "信号存在但已被过滤",
                "reason_summary": "；".join(item.get("top_reasons") or []) or "当前无摘要",
                "risk_level": "high" if item["intent_profile"].get("distribution_score", 0) >= 70 else "medium",
                "stealth_score": float(item["intent_profile"].get("accumulation_score", 0.0)),
                "breakout_score": float(item["intent_profile"].get("attack_score", 0.0)),
                "distribution_score": float(item["intent_profile"].get("distribution_score", 0.0)),
                "close": item["metrics"].get("close"),
                "return_5d_pct": item["metrics"].get("return_5d_pct"),
                "return_10d_pct": None,
                "return_20d_pct": item["metrics"].get("return_20d_pct"),
                "net_inflow_5d": None,
                "net_inflow_20d": None,
                "positive_inflow_ratio_10d": None,
                "dist_ma20_pct": None,
                "price_position_60d": None,
                "l2_vs_l1_strength": None,
                "l2_order_event_available": 1,
                "sentiment_heat_ratio": None,
                "market_cap": None,
                "feature_version": STRATEGY_VERSION_V2,
                "strategy_version": STRATEGY_VERSION_V2,
                "intent_profile": item.get("intent_profile", {}),
                "entry_allowed": item.get("entry_allowed", True),
                "entry_block_reasons": item.get("entry_block_reasons", []),
                "candidate_types": item.get("candidate_types", []),
                "selection_rank_score": replay_rank_score if replay_rank_score is not None else live_rank_score,
                "selection_rank_mode": "layer3_replay_validation" if replay_validation else "layer3_live_lifecycle_score",
                "lifecycle_phase": lifecycle_phase,
                "lifecycle_phase_label": lifecycle_phase_label,
                "action_label": action_label,
                "replay_return_pct": replay_return_pct,
                "replay_entry_date": trade.get("entry_date"),
                "replay_exit_signal_date": trade.get("exit_signal_date"),
                "replay_exit_reason": trade.get("exit_reason"),
            }
        )
    if replay_validation:
        items = sorted(
            items,
            key=lambda item: (
                0 if item.get("replay_return_pct") is not None else 1,
                -float(item.get("replay_return_pct") if item.get("replay_return_pct") is not None else -9999.0),
                str(item.get("symbol") or ""),
            ),
        )
    else:
        items = sorted(
            items,
            key=lambda item: (
                -float(item.get("selection_rank_score") or 0.0),
                -float(item.get("breakout_score") or 0.0),
                str(item.get("symbol") or ""),
            ),
        )
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    items = items[:output_limit]
    return {
        "trade_date": payload["trade_date"],
        "strategy": "v2",
        "params": asdict(active_params),
        "rank_mode": "layer3_replay_validation" if replay_validation else "layer3_live_lifecycle_score",
        "items": items,
    }


def evaluate_strategy_range_v2(
    start_date: str,
    end_date: str,
    *,
    top_n: int = 10,
    replay_end_date: Optional[str] = None,
) -> Dict[str, Any]:
    active_params = build_selection_v2_page_params()
    resolved_replay_end = _resolve_replay_end_date(end_date, replay_end_date, active_params)
    trading_days = pd.bdate_range(start_date, end_date).strftime("%Y-%m-%d").tolist()
    daily_results: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    max_top_n = max(1, int(top_n))

    for trade_date in trading_days:
        candidates_payload = get_candidates_v2_api(trade_date, limit=max_top_n)
        day_candidates: List[Dict[str, Any]] = []
        for candidate in candidates_payload.get("items", []):
            replay_payload = replay_symbol_v2(
                symbol=str(candidate["symbol"]),
                start_date=trade_date,
                end_date=resolved_replay_end,
                params=active_params,
            )
            trade = next(
                (item for item in replay_payload.get("trades", []) if str(item.get("signal_date")) == trade_date),
                None,
            )
            trade_record = None
            if trade:
                trade_record = {
                    **trade,
                    "rank": candidate.get("rank"),
                    "selection_rank_score": candidate.get("selection_rank_score"),
                    "lifecycle_phase": candidate.get("lifecycle_phase"),
                    "lifecycle_phase_label": candidate.get("lifecycle_phase_label"),
                    "action_label": candidate.get("action_label"),
                    "candidate_types": candidate.get("candidate_types", []),
                }
                trades.append(trade_record)
            day_candidates.append(
                {
                    "rank": candidate.get("rank"),
                    "symbol": candidate.get("symbol"),
                    "score": candidate.get("selection_rank_score"),
                    "lifecycle_phase_label": candidate.get("lifecycle_phase_label"),
                    "action_label": candidate.get("action_label"),
                    "entry_allowed": candidate.get("entry_allowed"),
                    "trade": trade_record,
                }
            )
        daily_results.append(
            {
                "trade_date": trade_date,
                "candidate_count": len(day_candidates),
                "trade_count": sum(1 for item in day_candidates if item.get("trade")),
                "candidates": day_candidates,
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "replay_end_date": resolved_replay_end,
        "strategy_version": STRATEGY_VERSION_V2,
        "rank_mode": "layer3_live_lifecycle_score",
        "top_n": max_top_n,
        "params": asdict(active_params),
        "summary": _summarize_trades(trades),
        "daily_results": daily_results,
        "trades": trades,
    }


def get_profile_v2_api(symbol: str, trade_date: Optional[str]) -> Dict[str, Any]:
    active_params = build_selection_v2_page_params()
    target_date = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
    lookback_start = (pd.Timestamp(target_date) - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    end_date = min((pd.Timestamp(target_date) + pd.Timedelta(days=120)).strftime("%Y-%m-%d"), pd.Timestamp.today().strftime("%Y-%m-%d"))
    replay = replay_symbol_v2(symbol, lookback_start, end_date, params=active_params)
    day_replay = replay_trade_date_v2(target_date, limit=50, params=active_params, symbols=[symbol], replay_end_date=end_date)
    candidate = next((item for item in day_replay["candidates"] if str(item["symbol"]).lower() == str(symbol).lower()), None)
    if candidate is None:
        screen = screen_candidates_v2(target_date, limit=50, params=active_params, symbols=[symbol])
        raw_candidate = next((item for item in screen["items"] if str(item["symbol"]).lower() == str(symbol).lower()), None)
        if raw_candidate is None:
            raw_candidate = {
                "symbol": symbol.lower(),
                "trade_date": target_date,
                "candidate_types": [],
                "quant_score": 0.0,
                "top_reasons": [],
                "warnings": [],
                "intent_profile": {},
                "entry_allowed": True,
                "entry_block_reasons": [],
            }
        candidate = {
            "symbol": raw_candidate["symbol"],
            "candidate_types": raw_candidate.get("candidate_types", []),
            "quant_score": raw_candidate.get("quant_score", 0.0),
            "top_reasons": raw_candidate.get("top_reasons", []),
            "warnings": raw_candidate.get("warnings", []),
            "intent_profile": raw_candidate.get("intent_profile", {}),
            "entry_allowed": raw_candidate.get("entry_allowed", True),
            "entry_block_reasons": raw_candidate.get("entry_block_reasons", []),
            "research": build_research_card_v2(symbol, target_date, raw_candidate),
            "trade": next((trade for trade in replay["trades"] if str(trade["signal_date"]) == target_date), None),
            "daily_state_count": len(replay["daily_states"]),
        }
    day_state = next((row for row in replay["daily_states"] if str(row["date"]) == target_date), None)
    research = candidate.get("research") or build_research_card_v2(
        symbol,
        target_date,
        {
            "symbol": symbol.lower(),
            "candidate_types": candidate.get("candidate_types", []),
            "top_reasons": candidate.get("top_reasons", []),
            "warnings": candidate.get("warnings", []),
        },
    )
    series = [
        {
            "trade_date": row["date"],
            "close": row.get("close"),
            "net_inflow": row.get("l2_main_net_ratio"),
            "activity_ratio": row.get("active_buy_strength"),
            "l1_main_net": row.get("order_imbalance_ratio"),
            "l2_main_net": row.get("l2_main_net_ratio"),
            "event_count": None,
        }
        for row in replay["daily_states"]
    ]
    event_timeline = [
        {
            "kind": "event",
            "time": item.get("time") or "",
            "event_type": item.get("source_type") or item.get("kind") or "",
            "source": item.get("source") or "",
            "content": item.get("content") or item.get("title") or "",
            "summary_text": None,
        }
        for item in research.get("event_timeline", [])
    ]
    sentiment = research.get("sentiment_snapshot") or {}
    if sentiment.get("available"):
        event_timeline.insert(
            0,
            {
                "kind": "daily_score",
                "time": sentiment.get("trade_date") or "",
                "event_type": "sentiment_daily_score",
                "source": "sentiment_daily_scores",
                "sentiment_score": sentiment.get("sentiment_score"),
                "direction_label": sentiment.get("direction_label"),
                "risk_tag": sentiment.get("risk_tag"),
                "summary_text": sentiment.get("summary_text"),
            },
        )
    intent = candidate.get("intent_profile") or {}
    return {
        "symbol": symbol.lower(),
        "trade_date": target_date,
        "latest_available_trade_date": replay["daily_states"][-1]["date"] if replay["daily_states"] else target_date,
        "requested_trade_date": target_date,
        "profile_date_fallback_used": False,
        "name": research.get("name") or symbol.lower(),
        "market_cap": research.get("market_cap"),
        "feature_version": STRATEGY_VERSION_V2,
        "strategy_version": STRATEGY_VERSION_V2,
        "params": asdict(active_params),
        "stealth_score": float(intent.get("accumulation_score", 0.0)),
        "stealth_signal": 1 if intent.get("intent_label") == "accumulation" else 0,
        "breakout_score": float(intent.get("attack_score", 0.0)),
        "confirm_signal": 1 if candidate.get("entry_allowed", True) else 0,
        "distribution_score": float(intent.get("distribution_score", 0.0)),
        "exit_signal": 1 if intent.get("exit_signal") else 0,
        "close": float(day_state.get("close") or 0.0) if day_state else 0.0,
        "return_20d_pct": day_state.get("return_20d_pct") if day_state else None,
        "breakout_vs_prev20_high_pct": None,
        "l2_vs_l1_strength": day_state.get("l2_main_net_ratio") if day_state else None,
        "l2_order_event_available": 1,
        "net_inflow_5d": None,
        "positive_inflow_ratio_10d": None,
        "sentiment_heat_ratio": None,
        "current_judgement": "可进场" if candidate.get("entry_allowed", True) else "已被入场过滤器拦截",
        "breakout_reason_summary": "；".join(candidate.get("top_reasons") or research.get("tracking_points") or []) or "当前无说明",
        "distribution_reason_summary": "；".join(candidate.get("warnings") or research.get("risk_points") or []) or "当前未见明显出货压力",
        "trade_plan": {
            "signal_date": target_date,
            "entry_date": candidate.get("trade", {}) and candidate["trade"].get("entry_date"),
            "entry_price": candidate.get("trade", {}) and candidate["trade"].get("entry_price"),
            "exit_signal_date": candidate.get("trade", {}) and candidate["trade"].get("exit_signal_date"),
            "exit_price": candidate.get("trade", {}) and candidate["trade"].get("exit_price"),
            "exit_reason": candidate.get("trade", {}) and candidate["trade"].get("exit_reason"),
            "exit_is_simulated": bool(candidate.get("trade")),
            "return_pct": candidate.get("trade", {}) and candidate["trade"].get("net_return_pct"),
        },
        "series": series,
        "event_timeline": event_timeline,
        "entry_allowed": candidate.get("entry_allowed", True),
        "entry_block_reasons": candidate.get("entry_block_reasons", []),
        "intent_profile": intent,
        "candidate_types": candidate.get("candidate_types", []),
        "research": research,
    }
