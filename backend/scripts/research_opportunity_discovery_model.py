#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db")
DEFAULT_SELECTION_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db")
DEFAULT_HEAT_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db")
MODEL_VERSION = "opportunity_discovery_trade_l2_v0_1"
OUT_DIR = ROOT / "data/selection/opportunity_discovery" / MODEL_VERSION


@dataclass(frozen=True)
class OpportunityConfig:
    start_date: str = "2025-01-02"
    end_date: str = "2026-05-14"
    horizon_days: int = 22
    validation_start: str = "2026-03-02"
    validation_end: Optional[str] = None
    min_signal_amount: float = 80_000_000.0
    min_train_amount: float = 30_000_000.0
    max_open_gap_up_pct: float = 6.8
    max_open_gap_down_pct: float = -5.5
    near_limit_up_ratio: float = 0.997
    max_signal_return_20d_pct: float = 95.0
    max_signal_distribution_score: float = 88.0
    buy_slippage_bp: float = 15.0
    sell_slippage_bp: float = 15.0
    round_trip_fee_bp: float = 20.0
    random_state: int = 42


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    target_profit_pct: float
    stop_loss_pct: Optional[float] = None
    trailing_activate_pct: Optional[float] = None
    trailing_drawdown_pct: Optional[float] = None
    time_exit_days: int = 22
    time_exit_price: str = "close"


EXIT_POLICIES = [
    ExitPolicy(name="tp15_else_day22_close", target_profit_pct=15.0),
    ExitPolicy(name="tp15_sl8_else_day22_close", target_profit_pct=15.0, stop_loss_pct=-8.0),
    ExitPolicy(name="tp15_sl10_else_day22_close", target_profit_pct=15.0, stop_loss_pct=-10.0),
    ExitPolicy(name="tp12_sl8_else_day22_close", target_profit_pct=12.0, stop_loss_pct=-8.0),
    ExitPolicy(name="tp20_sl8_else_day22_close", target_profit_pct=20.0, stop_loss_pct=-8.0),
    ExitPolicy(
        name="tp15_sl8_trail10_6_else_day22_close",
        target_profit_pct=15.0,
        stop_loss_pct=-8.0,
        trailing_activate_pct=10.0,
        trailing_drawdown_pct=6.0,
    ),
]


HOLDING_MODEL_POLICIES = [
    {
        "name": "hold_model_no_tp_stop12",
        "target_profit_pct": None,
        "hard_stop_pct": -12.0,
        "exit_threshold": 2.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
    },
    {
        "name": "hold_model_tp15_stop12",
        "target_profit_pct": 15.0,
        "hard_stop_pct": -12.0,
        "exit_threshold": 2.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
    },
    {
        "name": "hold_model_tp12_stop10",
        "target_profit_pct": 12.0,
        "hard_stop_pct": -10.0,
        "exit_threshold": 2.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
    },
]


CORE_FEATURES = [
    "close",
    "daily_return_pct",
    "return_3d_pct",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
    "volatility_10d",
    "volatility_20d",
    "dist_ma20_pct",
    "dist_ma60_pct",
    "price_position_20d",
    "price_position_60d",
    "breakout_vs_prev20_high_pct",
    "net_inflow_5d",
    "net_inflow_10d",
    "net_inflow_20d",
    "positive_inflow_ratio_5d",
    "positive_inflow_ratio_10d",
    "positive_inflow_ratio_20d",
    "main_activity_20d",
    "activity_ratio_5d",
    "activity_ratio_20d",
    "l1_main_net_3d",
    "l2_main_net_3d",
    "l2_vs_l1_strength",
    "stealth_score",
    "breakout_score",
    "distribution_score",
    "stealth_reason_strength",
    "breakout_reason_strength",
    "distribution_reason_strength",
    "l2_confirm_bonus",
    "heat_risk_score",
    "price_extension_score",
    "inflow_quality_score",
    "outflow_pressure_score",
    "l2_distribution_score",
    "total_amount",
    "total_volume",
    "trade_count",
    "l2_main_net_ratio",
    "l2_super_net_ratio",
    "l1_main_net_ratio",
    "l1_super_net_ratio",
    "active_buy_strength",
    "positive_l2_bar_ratio",
    "open_30m_l2_main_net_ratio",
    "last_30m_l2_main_net_ratio",
    "main_net_5d_ratio",
    "main_net_10d_ratio",
    "main_net_20d_ratio",
    "super_net_5d_ratio",
    "super_net_10d_ratio",
    "super_net_20d_ratio",
    "positive_main_day_ratio_10d",
    "positive_super_day_ratio_10d",
    "amount_anomaly_20d_atomic",
    "trade_count_anomaly_20d",
    "price_vs_prev20_high_pct_atomic",
    "max_drawdown_from_20d_high_pct",
    "signal_is_limit_up_close",
    "signal_limit_up_like",
    "signal_locked_limit_up_like",
    "signal_touch_limit_up",
    "signal_broken_limit_up",
    "hot_theme_best_rank",
    "hot_theme_score",
    "hot_theme_persistence_score",
    "hot_theme_member_count",
    "hot_theme_is_top10",
    "hot_theme_is_new_hot",
    "hot_theme_is_continuing_hot",
    "hot_theme_is_climax_hot",
    "hot_theme_is_fading",
    "market_advancing_ratio",
    "market_median_return_pct",
    "market_l2_main_net_ratio",
    "market_limit_up_count",
]

SHADOW_ORDERBOOK_FEATURES = [
    "order_imbalance_ratio",
    "cvd_ratio",
    "add_buy_ratio",
    "add_sell_ratio",
    "cancel_buy_ratio",
    "cancel_sell_ratio",
    "buy_support_ratio",
    "sell_pressure_ratio",
    "support_pressure_spread",
    "avg_book_imbalance_ratio",
    "close_book_imbalance_ratio",
    "bid_dominant_bar_count",
    "ask_dominant_bar_count",
    "thin_book_bar_count",
    "l2_order_event_available",
]

HOLD_FEATURES = [
    "holding_days",
    "unrealized_close_return_pct",
    "max_runup_so_far_pct",
    "drawdown_from_peak_pct",
    "max_drawdown_so_far_pct",
    "day_return_pct",
    "return_3d_from_hold_pct",
    "return_5d_from_hold_pct",
    "l2_main_net_ratio",
    "l2_super_net_ratio",
    "main_net_3d_hold_ratio",
    "super_net_3d_hold_ratio",
    "main_net_cum_hold_ratio",
    "super_net_cum_hold_ratio",
    "active_buy_strength",
    "positive_l2_bar_ratio",
    "amount_anomaly_20d_atomic",
    "trade_count_anomaly_20d",
    "price_position_20d",
    "return_20d_pct",
    "breakout_score",
    "stealth_score",
    "distribution_score",
    "market_advancing_ratio",
    "market_median_return_pct",
    "market_l2_main_net_ratio",
    "order_imbalance_ratio",
    "cvd_ratio",
    "support_pressure_spread",
    "avg_book_imbalance_ratio",
    "close_book_imbalance_ratio",
]


def _connect_ro(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(den, errors="coerce").replace(0, np.nan)
    return (pd.to_numeric(num, errors="coerce") / denominator).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _is_mainboard_10cm_symbol(symbol: str) -> bool:
    s = str(symbol).lower()
    return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if joblib is not None:
        joblib.dump(model, path)
        return
    with path.open("wb") as f:
        pickle.dump(model, f)


def _read_model(path: Path) -> Any:
    if joblib is not None:
        return joblib.load(path)
    with path.open("rb") as f:
        return pickle.load(f)


def _apply_buy_cost(price: float, config: OpportunityConfig) -> float:
    slip = float(config.buy_slippage_bp) / 10_000.0
    fee = (float(config.round_trip_fee_bp) / 10_000.0) / 2.0
    return float(price) * (1.0 + slip + fee)


def _apply_sell_cost(price: float, config: OpportunityConfig) -> float:
    slip = float(config.sell_slippage_bp) / 10_000.0
    fee = (float(config.round_trip_fee_bp) / 10_000.0) / 2.0
    return float(price) * (1.0 - slip - fee)


def load_selection_features(start_date: str, end_date: str, selection_db: Path) -> pd.DataFrame:
    sql = """
        SELECT
            lower(f.symbol) AS symbol,
            f.trade_date,
            f.close,
            f.prev_close,
            f.daily_return_pct,
            f.return_3d_pct,
            f.return_5d_pct,
            f.return_10d_pct,
            f.return_20d_pct,
            f.volatility_10d,
            f.volatility_20d,
            f.ma20,
            f.ma60,
            f.dist_ma20_pct,
            f.dist_ma60_pct,
            f.price_position_20d,
            f.price_position_60d,
            f.breakout_vs_prev20_high_pct,
            f.net_inflow_5d,
            f.net_inflow_10d,
            f.net_inflow_20d,
            f.positive_inflow_ratio_5d,
            f.positive_inflow_ratio_10d,
            f.positive_inflow_ratio_20d,
            f.main_activity_20d,
            f.activity_ratio_5d,
            f.activity_ratio_20d,
            f.l1_main_net_3d,
            f.l2_main_net_3d,
            f.l2_vs_l1_strength,
            f.l2_order_event_available,
            f.l2_add_buy_3d,
            f.l2_add_sell_3d,
            f.l2_cancel_buy_3d,
            f.l2_cancel_sell_3d,
            f.l2_cvd_3d,
            f.l2_oib_3d,
            f.sentiment_event_count_5d,
            f.sentiment_event_count_20d,
            f.sentiment_heat_ratio,
            f.sentiment_score,
            f.market_cap,
            f.name,
            s.stealth_score,
            s.breakout_score,
            s.distribution_score,
            s.stealth_reason_strength,
            s.breakout_reason_strength,
            s.distribution_reason_strength,
            s.l2_confirm_bonus,
            s.heat_risk_score,
            s.price_extension_score,
            s.inflow_quality_score,
            s.outflow_pressure_score,
            s.sentiment_heat_score,
            s.l2_distribution_score
        FROM selection_feature_daily AS f
        LEFT JOIN selection_signal_daily AS s
          ON s.symbol = f.symbol
         AND s.trade_date = f.trade_date
         AND s.feature_version = f.feature_version
        WHERE f.trade_date >= ? AND f.trade_date <= ?
    """
    with _connect_ro(selection_db) as conn:
        df = pd.read_sql_query(sql, conn, params=[start_date, end_date])
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).str.lower()
    df = df[df["symbol"].map(_is_mainboard_10cm_symbol)].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for col in df.columns:
        if col not in {"symbol", "trade_date"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_atomic_daily(start_date: str, end_date: str, atomic_db: Path) -> pd.DataFrame:
    sql = """
        SELECT
            lower(t.symbol) AS symbol,
            t.trade_date,
            t.open,
            t.high,
            t.low,
            t.close AS atomic_close,
            t.total_amount,
            t.total_volume,
            t.trade_count,
            t.l1_main_net_amount,
            t.l1_super_net_amount,
            t.l2_main_net_amount,
            t.l2_super_net_amount,
            t.l1_buy_ratio,
            t.l1_sell_ratio,
            t.l2_buy_ratio,
            t.l2_sell_ratio,
            t.open_30m_l2_main_net_amount,
            t.last_30m_l2_main_net_amount,
            t.positive_l2_net_bar_count,
            t.negative_l2_net_bar_count,
            o.add_buy_amount,
            o.add_sell_amount,
            o.cancel_buy_amount,
            o.cancel_sell_amount,
            o.cvd_delta_amount,
            o.oib_delta_amount,
            o.buy_support_ratio,
            o.sell_pressure_ratio,
            o.order_event_count,
            b.avg_book_imbalance_ratio,
            b.close_book_imbalance_ratio,
            b.avg_book_depth_ratio,
            b.close_book_depth_ratio,
            b.bid_dominant_bar_count,
            b.ask_dominant_bar_count,
            b.thin_book_bar_count,
            b.valid_bucket_count,
            l.board_type,
            l.risk_flag_type,
            l.prev_close AS limit_prev_close,
            l.up_limit_price,
            l.down_limit_price,
            l.limit_pct,
            l.touch_limit_up,
            l.touch_limit_down,
            l.is_limit_up_close,
            l.is_limit_down_close,
            l.broken_limit_up,
            l.broken_limit_down
        FROM atomic_trade_daily AS t
        LEFT JOIN atomic_order_daily AS o
          ON o.symbol = t.symbol
         AND o.trade_date = t.trade_date
        LEFT JOIN atomic_book_state_daily AS b
          ON b.symbol = t.symbol
         AND b.trade_date = t.trade_date
        LEFT JOIN atomic_limit_state_daily AS l
          ON l.symbol = t.symbol
         AND l.trade_date = t.trade_date
        WHERE t.trade_date >= ? AND t.trade_date <= ?
        ORDER BY lower(t.symbol), t.trade_date
    """
    with _connect_ro(atomic_db) as conn:
        df = pd.read_sql_query(sql, conn, params=[start_date, end_date])
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).str.lower()
    df = df[df["symbol"].map(_is_mainboard_10cm_symbol)].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    numeric = [col for col in df.columns if col not in {"symbol", "trade_date", "board_type", "risk_flag_type"}]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["risk_flag_type"] = df["risk_flag_type"].fillna("normal").astype(str)
    return df


def add_atomic_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_values(["symbol", "trade_date"]).copy()
    out["l2_main_net_ratio"] = _safe_ratio(out["l2_main_net_amount"], out["total_amount"])
    out["l2_super_net_ratio"] = _safe_ratio(out["l2_super_net_amount"], out["total_amount"])
    out["l1_main_net_ratio"] = _safe_ratio(out["l1_main_net_amount"], out["total_amount"])
    out["l1_super_net_ratio"] = _safe_ratio(out["l1_super_net_amount"], out["total_amount"])
    out["active_buy_strength"] = out["l2_buy_ratio"] - out["l2_sell_ratio"]
    bar_total = out["positive_l2_net_bar_count"] + out["negative_l2_net_bar_count"]
    out["positive_l2_bar_ratio"] = _safe_ratio(out["positive_l2_net_bar_count"], bar_total)
    out["open_30m_l2_main_net_ratio"] = _safe_ratio(out["open_30m_l2_main_net_amount"], out["total_amount"])
    out["last_30m_l2_main_net_ratio"] = _safe_ratio(out["last_30m_l2_main_net_amount"], out["total_amount"])
    out["order_imbalance_ratio"] = _safe_ratio(out["oib_delta_amount"], out["total_amount"])
    out["cvd_ratio"] = _safe_ratio(out["cvd_delta_amount"], out["total_amount"])
    out["add_buy_ratio"] = _safe_ratio(out["add_buy_amount"], out["total_amount"])
    out["add_sell_ratio"] = _safe_ratio(out["add_sell_amount"], out["total_amount"])
    out["cancel_buy_ratio"] = _safe_ratio(out["cancel_buy_amount"], out["total_amount"])
    out["cancel_sell_ratio"] = _safe_ratio(out["cancel_sell_amount"], out["total_amount"])
    out["support_pressure_spread"] = out["buy_support_ratio"].fillna(0.0) - out["sell_pressure_ratio"].fillna(0.0)

    frames: List[pd.DataFrame] = []
    for _, g0 in out.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").copy()
        amount_5 = g["total_amount"].rolling(5, min_periods=3).sum()
        amount_10 = g["total_amount"].rolling(10, min_periods=5).sum()
        amount_20 = g["total_amount"].rolling(20, min_periods=8).sum()
        g["main_net_5d_ratio"] = (g["l2_main_net_amount"].rolling(5, min_periods=3).sum() / amount_5.replace(0, np.nan)).fillna(0.0)
        g["main_net_10d_ratio"] = (g["l2_main_net_amount"].rolling(10, min_periods=5).sum() / amount_10.replace(0, np.nan)).fillna(0.0)
        g["main_net_20d_ratio"] = (g["l2_main_net_amount"].rolling(20, min_periods=8).sum() / amount_20.replace(0, np.nan)).fillna(0.0)
        g["super_net_5d_ratio"] = (g["l2_super_net_amount"].rolling(5, min_periods=3).sum() / amount_5.replace(0, np.nan)).fillna(0.0)
        g["super_net_10d_ratio"] = (g["l2_super_net_amount"].rolling(10, min_periods=5).sum() / amount_10.replace(0, np.nan)).fillna(0.0)
        g["super_net_20d_ratio"] = (g["l2_super_net_amount"].rolling(20, min_periods=8).sum() / amount_20.replace(0, np.nan)).fillna(0.0)
        g["positive_main_day_ratio_10d"] = g["l2_main_net_amount"].gt(0).rolling(10, min_periods=5).mean().fillna(0.0)
        g["positive_super_day_ratio_10d"] = g["l2_super_net_amount"].gt(0).rolling(10, min_periods=5).mean().fillna(0.0)
        g["amount_ma20_atomic"] = g["total_amount"].rolling(20, min_periods=8).mean()
        g["trade_count_ma20_atomic"] = g["trade_count"].rolling(20, min_periods=8).mean()
        g["amount_anomaly_20d_atomic"] = (g["total_amount"] / g["amount_ma20_atomic"].replace(0, np.nan)).fillna(0.0)
        g["trade_count_anomaly_20d"] = (g["trade_count"] / g["trade_count_ma20_atomic"].replace(0, np.nan)).fillna(0.0)
        prev20_high = g["high"].shift(1).rolling(20, min_periods=8).max()
        recent20_high = g["high"].rolling(20, min_periods=8).max()
        g["price_vs_prev20_high_pct_atomic"] = ((g["atomic_close"] / prev20_high.replace(0, np.nan)) - 1.0).fillna(0.0) * 100.0
        g["max_drawdown_from_20d_high_pct"] = ((g["atomic_close"] / recent20_high.replace(0, np.nan)) - 1.0).fillna(0.0) * 100.0
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def load_heat_features(start_date: str, end_date: str, heat_db: Path) -> pd.DataFrame:
    if not heat_db.exists():
        return pd.DataFrame()
    sql = """
        SELECT
            lower(m.symbol) AS symbol,
            m.trade_date,
            MIN(h.hot_rank) AS hot_theme_best_rank,
            MAX(h.hot_score) AS hot_theme_score,
            MAX(h.persistence_score) AS hot_theme_persistence_score,
            COUNT(DISTINCT m.theme_id) AS hot_theme_member_count,
            MAX(CASE WHEN h.hot_rank <= 10 THEN 1 ELSE 0 END) AS hot_theme_is_top10,
            MAX(CASE WHEN lc.is_new_hot = 1 THEN 1 ELSE 0 END) AS hot_theme_is_new_hot,
            MAX(CASE WHEN lc.is_continuing_hot = 1 THEN 1 ELSE 0 END) AS hot_theme_is_continuing_hot,
            MAX(CASE WHEN lc.is_climax_hot = 1 THEN 1 ELSE 0 END) AS hot_theme_is_climax_hot,
            MAX(CASE WHEN lc.is_fading = 1 THEN 1 ELSE 0 END) AS hot_theme_is_fading
        FROM fine_theme_member_daily AS m
        JOIN fine_theme_heat_daily AS h
          ON h.trade_date = m.trade_date
         AND h.theme_id = m.theme_id
        LEFT JOIN fine_theme_lifecycle_daily AS lc
          ON lc.trade_date = m.trade_date
         AND lc.theme_id = m.theme_id
        WHERE m.trade_date >= ? AND m.trade_date <= ?
          AND h.hot_rank <= 30
        GROUP BY lower(m.symbol), m.trade_date
    """
    try:
        with _connect_ro(heat_db) as conn:
            if not (_table_exists(conn, "fine_theme_member_daily") and _table_exists(conn, "fine_theme_heat_daily")):
                return pd.DataFrame()
            df = pd.read_sql_query(sql, conn, params=[start_date, end_date])
    except sqlite3.OperationalError:
        return pd.DataFrame()
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).str.lower()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for col in df.columns:
        if col not in {"symbol", "trade_date"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def add_market_features(panel: pd.DataFrame) -> pd.DataFrame:
    day = panel.copy()
    daily_return = ((day["atomic_close"] / day["limit_prev_close"].replace(0, np.nan)) - 1.0).replace([np.inf, -np.inf], np.nan) * 100.0
    day["atomic_daily_return_pct"] = daily_return.fillna(0.0)
    grouped = day.groupby("trade_date", as_index=False).agg(
        market_advancing_ratio=("atomic_daily_return_pct", lambda s: float((s > 0).mean())),
        market_median_return_pct=("atomic_daily_return_pct", "median"),
        market_total_amount=("total_amount", "sum"),
        market_l2_main_net=("l2_main_net_amount", "sum"),
        market_limit_up_count=("is_limit_up_close", "sum"),
    )
    grouped["market_l2_main_net_ratio"] = _safe_ratio(grouped["market_l2_main_net"], grouped["market_total_amount"])
    keep = [
        "trade_date",
        "market_advancing_ratio",
        "market_median_return_pct",
        "market_l2_main_net_ratio",
        "market_limit_up_count",
    ]
    return panel.merge(grouped[keep], on="trade_date", how="left")


def build_labels(atomic_panel: pd.DataFrame, config: OpportunityConfig) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    df = atomic_panel.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    for symbol, g0 in df.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        n = len(g)
        for i in range(0, n - 1):
            entry_i = i + 1
            end_i = min(n, entry_i + int(config.horizon_days))
            future = g.iloc[entry_i:end_i]
            if len(future) < int(config.horizon_days):
                continue
            signal = g.iloc[i]
            entry = g.iloc[entry_i]
            entry_open = _to_float(entry.get("open"))
            signal_close = _to_float(signal.get("atomic_close"))
            if entry_open <= 0 or signal_close <= 0:
                continue
            highs = future["high"].astype(float).to_numpy()
            lows = future["low"].astype(float).to_numpy()
            closes = future["atomic_close"].astype(float).to_numpy()
            best_offset = int(np.nanargmax(highs))
            max_high = float(highs[best_offset])
            min_low_to_mfe = float(np.nanmin(lows[: best_offset + 1]))
            min_low_22d = float(np.nanmin(lows))
            max_runup_pct = (max_high / entry_open - 1.0) * 100.0
            mdd_to_mfe_pct = (min_low_to_mfe / entry_open - 1.0) * 100.0
            max_drawdown_22d_pct = (min_low_22d / entry_open - 1.0) * 100.0
            close_return_22d_pct = (float(closes[-1]) / entry_open - 1.0) * 100.0
            entry_gap_pct = (entry_open / signal_close - 1.0) * 100.0
            up_limit_price = _to_float(entry.get("up_limit_price"))
            if up_limit_price <= 0:
                prev_for_limit = _to_float(entry.get("limit_prev_close"), signal_close)
                if prev_for_limit <= 0:
                    prev_for_limit = signal_close
                up_limit_price = prev_for_limit * 1.10
            near_limit_up = bool(up_limit_price > 0 and entry_open >= up_limit_price * float(config.near_limit_up_ratio))
            locked_limit_up = bool(near_limit_up and _to_float(entry.get("low")) >= up_limit_price * float(config.near_limit_up_ratio))
            high_gap_penalty = max(0.0, entry_gap_pct - 3.5) * 1.4
            path_penalty = max(0.0, -mdd_to_mfe_pct - 7.0) * 0.85 + max(0.0, -max_drawdown_22d_pct - 13.0) * 0.20
            block_penalty = 18.0 if locked_limit_up else (8.0 if near_limit_up else 0.0)
            opportunity_score = max_runup_pct - high_gap_penalty - path_penalty - block_penalty

            def first_hit(threshold: float) -> int:
                hit = np.where((highs / entry_open - 1.0) * 100.0 >= threshold)[0]
                return int(hit[0] + 1) if len(hit) else 0

            def first_drawdown(threshold: float) -> int:
                hit = np.where((lows / entry_open - 1.0) * 100.0 <= -abs(threshold))[0]
                return int(hit[0] + 1) if len(hit) else 0

            hit10_day = first_hit(10.0)
            hit15_day = first_hit(15.0)
            hit20_day = first_hit(20.0)
            dd8_day = first_drawdown(8.0)
            rows.append(
                {
                    "symbol": str(symbol),
                    "trade_date": str(signal["trade_date"]),
                    "entry_date": str(entry["trade_date"]),
                    "label_end_date": str(future.iloc[-1]["trade_date"]),
                    "entry_open": round(entry_open, 4),
                    "entry_gap_pct": round(entry_gap_pct, 4),
                    "entry_near_limit_up": int(near_limit_up),
                    "entry_locked_limit_up": int(locked_limit_up),
                    "future_window_days": int(len(future)),
                    "max_runup_22d_pct": round(max_runup_pct, 4),
                    "mdd_to_mfe_pct": round(mdd_to_mfe_pct, 4),
                    "max_drawdown_22d_pct": round(max_drawdown_22d_pct, 4),
                    "close_return_22d_pct": round(close_return_22d_pct, 4),
                    "days_to_mfe": int(best_offset + 1),
                    "hit10_day": hit10_day,
                    "hit15_day": hit15_day,
                    "hit20_day": hit20_day,
                    "dd8_day": dd8_day,
                    "hit10_before_dd8": int(hit10_day > 0 and (dd8_day == 0 or hit10_day <= dd8_day)),
                    "hit15_before_dd8": int(hit15_day > 0 and (dd8_day == 0 or hit15_day <= dd8_day)),
                    "hit20_before_dd8": int(hit20_day > 0 and (dd8_day == 0 or hit20_day <= dd8_day)),
                    "opportunity_score": round(float(np.clip(opportunity_score, -40.0, 90.0)), 4),
                }
            )
    return pd.DataFrame(rows)


def build_dataset(config: OpportunityConfig, atomic_db: Path, selection_db: Path, heat_db: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    selection = load_selection_features(config.start_date, config.end_date, selection_db)
    atomic = add_atomic_features(load_atomic_daily(config.start_date, config.end_date, atomic_db))
    atomic = add_market_features(atomic)
    heat = load_heat_features(config.start_date, config.end_date, heat_db)

    panel = selection.merge(atomic, on=["symbol", "trade_date"], how="inner", suffixes=("", "_atomic_dup"))
    if not heat.empty:
        panel = panel.merge(heat, on=["symbol", "trade_date"], how="left")
    defaults = {
        "hot_theme_best_rank": 999.0,
        "hot_theme_score": 0.0,
        "hot_theme_persistence_score": 0.0,
        "hot_theme_member_count": 0.0,
        "hot_theme_is_top10": 0.0,
        "hot_theme_is_new_hot": 0.0,
        "hot_theme_is_continuing_hot": 0.0,
        "hot_theme_is_climax_hot": 0.0,
        "hot_theme_is_fading": 0.0,
        "board_type": "",
        "risk_flag_type": "normal",
    }
    for col, default in defaults.items():
        if col not in panel.columns:
            panel[col] = default
        else:
            panel[col] = panel[col].fillna(default)
    prev_for_limit = pd.to_numeric(panel.get("limit_prev_close", 0.0), errors="coerce")
    fallback_prev = pd.to_numeric(panel.get("prev_close", 0.0), errors="coerce")
    prev_for_limit = prev_for_limit.where(prev_for_limit > 0, fallback_prev).fillna(0.0)
    close_for_limit = pd.to_numeric(panel.get("atomic_close", panel.get("close", 0.0)), errors="coerce").fillna(0.0)
    high_for_limit = pd.to_numeric(panel.get("high", close_for_limit), errors="coerce").fillna(0.0)
    low_for_limit = pd.to_numeric(panel.get("low", close_for_limit), errors="coerce").fillna(0.0)
    open_for_limit = pd.to_numeric(panel.get("open", close_for_limit), errors="coerce").fillna(0.0)
    up_limit_price = pd.to_numeric(panel.get("up_limit_price", 0.0), errors="coerce").fillna(0.0)
    inferred_up_limit = np.where(up_limit_price > 0, up_limit_price, prev_for_limit * 1.10)
    inferred_limit_return = np.where(prev_for_limit > 0, (close_for_limit / prev_for_limit - 1.0) * 100.0, 0.0)
    signal_limit_up_like = (
        (prev_for_limit > 0)
        & (
            (pd.to_numeric(panel.get("is_limit_up_close", 0), errors="coerce").fillna(0.0) > 0)
            | (close_for_limit >= inferred_up_limit * 0.995)
            | (inferred_limit_return >= 9.85)
        )
    )
    signal_locked_limit_up_like = signal_limit_up_like & (open_for_limit >= inferred_up_limit * 0.995) & (low_for_limit >= inferred_up_limit * 0.995)
    panel["signal_is_limit_up_close"] = signal_limit_up_like.astype(float)
    panel["signal_limit_up_like"] = signal_limit_up_like.astype(float)
    panel["signal_locked_limit_up_like"] = signal_locked_limit_up_like.astype(float)
    panel["signal_touch_limit_up"] = (
        (pd.to_numeric(panel.get("touch_limit_up", 0), errors="coerce").fillna(0.0) > 0)
        | (high_for_limit >= inferred_up_limit * 0.995)
    ).astype(float)
    panel["signal_broken_limit_up"] = pd.to_numeric(panel.get("broken_limit_up", 0), errors="coerce").fillna(0.0)

    labels = build_labels(atomic, config)
    data = panel.merge(labels, on=["symbol", "trade_date"], how="inner")
    data = data[data["risk_flag_type"].fillna("normal").eq("normal")].copy()
    data = data[pd.to_numeric(data["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_train_amount)].copy()
    data = data[pd.to_numeric(data["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_signal_return_20d_pct)].copy()
    data = data[pd.to_numeric(data["distribution_score"], errors="coerce").fillna(0.0) <= float(config.max_signal_distribution_score)].copy()
    return data, panel


def available_feature_columns(df: pd.DataFrame, include_orderbook: bool = False) -> List[str]:
    candidates = CORE_FEATURES + (SHADOW_ORDERBOOK_FEATURES if include_orderbook else [])
    cols = [col for col in candidates if col in df.columns]
    return cols


def _score_rule_baseline(df: pd.DataFrame) -> pd.Series:
    def norm(s: pd.Series, low: float, high: float) -> pd.Series:
        return ((pd.to_numeric(s, errors="coerce").fillna(0.0) - low) / (high - low)).clip(0.0, 1.0) * 100.0

    score = (
        0.16 * norm(df.get("breakout_score", 0.0), 45, 85)
        + 0.13 * norm(df.get("stealth_score", 0.0), 45, 85)
        + 0.14 * norm(df.get("l2_main_net_ratio", 0.0), -0.01, 0.05)
        + 0.10 * norm(df.get("l2_super_net_ratio", 0.0), -0.006, 0.03)
        + 0.11 * norm(df.get("active_buy_strength", 0.0), -1.0, 8.0)
        + 0.10 * norm(df.get("amount_anomaly_20d_atomic", 0.0), 0.8, 2.4)
        + 0.08 * norm(df.get("price_position_20d", 0.0), 0.25, 0.88)
        + 0.06 * norm(1000.0 - pd.to_numeric(df.get("hot_theme_best_rank", 999.0), errors="coerce").fillna(999.0), 970, 999)
        + 0.07 * norm(df.get("market_advancing_ratio", 0.0), 0.35, 0.65)
        - 0.09 * norm(df.get("distribution_score", 0.0), 55, 90)
        - 0.06 * norm(df.get("return_20d_pct", 0.0), 40, 100)
    )
    return score.fillna(0.0)


def _fit_model(train: pd.DataFrame, feature_cols: Sequence[str], config: OpportunityConfig) -> Pipeline:
    X = train[list(feature_cols)]
    y = pd.to_numeric(train["opportunity_score"], errors="coerce").fillna(0.0)
    sample_weight = 1.0 + (pd.to_numeric(train["max_runup_22d_pct"], errors="coerce").fillna(0.0) >= 15.0).astype(float) * 1.5
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.055,
        max_iter=220,
        max_leaf_nodes=31,
        min_samples_leaf=45,
        l2_regularization=0.04,
        random_state=int(config.random_state),
    )
    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )
    pipe.fit(X, y, model__sample_weight=sample_weight)
    return pipe


def _feature_importance_proxy(train: pd.DataFrame, feature_cols: Sequence[str], config: OpportunityConfig) -> pd.DataFrame:
    sample = train.sample(n=min(80_000, len(train)), random_state=int(config.random_state)) if len(train) > 80_000 else train
    X = sample[list(feature_cols)].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = pd.to_numeric(sample["opportunity_score"], errors="coerce").fillna(0.0)
    rf = RandomForestRegressor(
        n_estimators=80,
        max_depth=7,
        min_samples_leaf=80,
        max_features="sqrt",
        n_jobs=-1,
        random_state=int(config.random_state),
    )
    rf.fit(X, y)
    out = pd.DataFrame({"feature": list(feature_cols), "importance": rf.feature_importances_})
    return out.sort_values("importance", ascending=False)


def _evaluate_topk(df: pd.DataFrame, score_col: str, ks: Sequence[int] = (1, 3, 5, 10)) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    daily_rows: List[Dict[str, Any]] = []
    if df.empty:
        return {"summary": [], "daily": []}
    ranked = df.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True]).copy()
    for k in ks:
        picks = ranked.groupby("trade_date", as_index=False).head(int(k)).copy()
        if picks.empty:
            continue
        rows.append(
            {
                "score_col": score_col,
                "top_k": int(k),
                "days": int(picks["trade_date"].nunique()),
                "picks": int(len(picks)),
                "avg_max_runup_22d_pct": round(float(picks["max_runup_22d_pct"].mean()), 4),
                "median_max_runup_22d_pct": round(float(picks["max_runup_22d_pct"].median()), 4),
                "hit10_rate": round(float((picks["max_runup_22d_pct"] >= 10.0).mean()), 4),
                "hit15_rate": round(float((picks["max_runup_22d_pct"] >= 15.0).mean()), 4),
                "hit20_rate": round(float((picks["max_runup_22d_pct"] >= 20.0).mean()), 4),
                "hit15_before_dd8_rate": round(float(picks["hit15_before_dd8"].mean()), 4),
                "avg_mdd_to_mfe_pct": round(float(picks["mdd_to_mfe_pct"].mean()), 4),
                "avg_entry_gap_pct": round(float(picks["entry_gap_pct"].mean()), 4),
                "entry_locked_limit_up_rate": round(float(picks["entry_locked_limit_up"].mean()), 4),
                "avg_opportunity_score": round(float(picks["opportunity_score"].mean()), 4),
            }
        )
    top3 = ranked.groupby("trade_date", as_index=False).head(3)
    for date, g in top3.groupby("trade_date", sort=True):
        daily_rows.append(
            {
                "trade_date": str(date),
                "symbols": ",".join(g["symbol"].astype(str).tolist()),
                "score_col": score_col,
                "avg_score": round(float(g[score_col].mean()), 4),
                "best_max_runup_22d_pct": round(float(g["max_runup_22d_pct"].max()), 4),
                "avg_max_runup_22d_pct": round(float(g["max_runup_22d_pct"].mean()), 4),
                "hit15_count": int((g["max_runup_22d_pct"] >= 15.0).sum()),
                "locked_count": int(g["entry_locked_limit_up"].sum()),
            }
        )
    return {"summary": rows, "daily": daily_rows}


def _apply_historical_entry_filter(df: pd.DataFrame, config: OpportunityConfig) -> pd.DataFrame:
    out = df.copy()
    return out[
        (pd.to_numeric(out["entry_locked_limit_up"], errors="coerce").fillna(0.0) <= 0)
        & (pd.to_numeric(out["entry_gap_pct"], errors="coerce").fillna(0.0) <= float(config.max_open_gap_up_pct))
        & (pd.to_numeric(out["entry_gap_pct"], errors="coerce").fillna(0.0) >= float(config.max_open_gap_down_pct))
        & (pd.to_numeric(out["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_signal_amount))
    ].copy()


def _future_path_map(
    atomic_panel: pd.DataFrame,
    config: OpportunityConfig,
    keys: Optional[Iterable[Tuple[str, str]]] = None,
) -> Dict[Tuple[str, str], pd.DataFrame]:
    out: Dict[Tuple[str, str], pd.DataFrame] = {}
    wanted = {(str(symbol), str(date)) for symbol, date in keys} if keys is not None else None
    df = atomic_panel.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    for symbol, g0 in df.groupby("symbol", sort=False):
        if wanted is not None and not any(item[0] == str(symbol) for item in wanted):
            continue
        g = g0.sort_values("trade_date").reset_index(drop=True)
        n = len(g)
        for i in range(0, n - 1):
            key = (str(symbol), str(g.loc[i, "trade_date"]))
            if wanted is not None and key not in wanted:
                continue
            entry_i = i + 1
            end_i = min(n, entry_i + int(config.horizon_days))
            future = g.iloc[entry_i:end_i].copy()
            if len(future) < int(config.horizon_days):
                continue
            out[key] = future
    return out


def _simulate_exit_policy(
    future: pd.DataFrame,
    policy: ExitPolicy,
    config: OpportunityConfig,
) -> Dict[str, Any]:
    if future.empty:
        return {
            "exit_reason": "no_future_path",
            "gross_return_pct": 0.0,
            "net_return_pct": 0.0,
            "holding_days": 0,
        }
    entry = future.iloc[0]
    gross_entry = _to_float(entry.get("open"))
    if gross_entry <= 0:
        return {
            "exit_reason": "bad_entry_price",
            "gross_return_pct": 0.0,
            "net_return_pct": 0.0,
            "holding_days": 0,
        }
    entry_price = _apply_buy_cost(gross_entry, config)
    peak_high = gross_entry
    max_runup = -999.0
    max_drawdown = 999.0
    exit_price = _to_float(future.iloc[-1].get(policy.time_exit_price, future.iloc[-1].get("atomic_close")))
    exit_date = str(future.iloc[-1]["trade_date"])
    exit_reason = "time_exit_day22"
    holding_days = int(len(future))
    target_price = gross_entry * (1.0 + float(policy.target_profit_pct) / 100.0)
    stop_price = gross_entry * (1.0 + float(policy.stop_loss_pct) / 100.0) if policy.stop_loss_pct is not None else None

    for offset, row in enumerate(future.itertuples(index=False), start=1):
        open_p = _to_float(getattr(row, "open", 0.0))
        high_p = _to_float(getattr(row, "high", 0.0))
        low_p = _to_float(getattr(row, "low", 0.0))
        close_p = _to_float(getattr(row, "atomic_close", 0.0))
        trade_date = str(getattr(row, "trade_date"))
        if open_p <= 0 or high_p <= 0 or low_p <= 0:
            continue
        peak_high = max(peak_high, high_p)
        max_runup = max(max_runup, (high_p / gross_entry - 1.0) * 100.0)
        max_drawdown = min(max_drawdown, (low_p / gross_entry - 1.0) * 100.0)

        stop_hit = offset >= 2 and stop_price is not None and low_p <= stop_price
        target_hit = offset >= 2 and high_p >= target_price
        if stop_hit and target_hit:
            # 日线无法知道先后，按保守原则先认止损。
            exit_price = stop_price if open_p > stop_price else open_p
            exit_date = trade_date
            exit_reason = "stop_loss_same_day_as_target"
            holding_days = offset
            break
        if stop_hit:
            exit_price = stop_price if open_p > stop_price else open_p
            exit_date = trade_date
            exit_reason = "stop_loss"
            holding_days = offset
            break
        if target_hit:
            exit_price = target_price if open_p < target_price else open_p
            exit_date = trade_date
            exit_reason = "take_profit"
            holding_days = offset
            break
        if (
            policy.trailing_activate_pct is not None
            and policy.trailing_drawdown_pct is not None
            and offset >= 2
            and (peak_high / gross_entry - 1.0) * 100.0 >= float(policy.trailing_activate_pct)
        ):
            trail_price = peak_high * (1.0 - float(policy.trailing_drawdown_pct) / 100.0)
            if low_p <= trail_price:
                exit_price = trail_price if open_p > trail_price else open_p
                exit_date = trade_date
                exit_reason = "trailing_stop"
                holding_days = offset
                break
        if offset >= int(policy.time_exit_days):
            exit_price = close_p if close_p > 0 else open_p
            exit_date = trade_date
            exit_reason = "time_exit_day22"
            holding_days = offset
            break

    if max_runup < -100:
        max_runup = (exit_price / gross_entry - 1.0) * 100.0
    if max_drawdown > 100:
        max_drawdown = (exit_price / gross_entry - 1.0) * 100.0
    net_exit = _apply_sell_cost(exit_price, config)
    gross_return = (exit_price / gross_entry - 1.0) * 100.0
    net_return = (net_exit / entry_price - 1.0) * 100.0
    return {
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "gross_entry_price": round(gross_entry, 4),
        "gross_exit_price": round(float(exit_price), 4),
        "gross_return_pct": round(float(gross_return), 4),
        "net_return_pct": round(float(net_return), 4),
        "holding_days": int(holding_days),
        "max_runup_before_exit_pct": round(float(max_runup), 4),
        "max_drawdown_before_exit_pct": round(float(max_drawdown), 4),
    }


def _trade_summary(trades: pd.DataFrame, policy_name: str, top_k: int) -> Dict[str, Any]:
    if trades.empty:
        return {"policy": policy_name, "top_k": int(top_k), "trades": 0}
    returns = pd.to_numeric(trades["net_return_pct"], errors="coerce").fillna(0.0)
    equity = (1.0 + returns / 100.0).cumprod()
    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    gross_profit = float(returns[returns > 0].sum())
    gross_loss = float(returns[returns < 0].sum())
    return {
        "policy": policy_name,
        "top_k": int(top_k),
        "trades": int(len(trades)),
        "days": int(trades["trade_date"].nunique()) if "trade_date" in trades else 0,
        "avg_net_return_pct": round(float(returns.mean()), 4),
        "median_net_return_pct": round(float(returns.median()), 4),
        "win_rate": round(float((returns > 0).mean()), 4),
        "hit_target_rate": round(float(trades["exit_reason"].astype(str).str.contains("take_profit").mean()), 4),
        "stop_loss_rate": round(float(trades["exit_reason"].astype(str).str.contains("stop_loss").mean()), 4),
        "time_exit_rate": round(float(trades["exit_reason"].astype(str).eq("time_exit_day22").mean()), 4),
        "avg_holding_days": round(float(pd.to_numeric(trades["holding_days"], errors="coerce").fillna(0.0).mean()), 2),
        "min_net_return_pct": round(float(returns.min()), 4),
        "max_net_return_pct": round(float(returns.max()), 4),
        "compound_return_pct_equal_1x": round(float((equity.iloc[-1] - 1.0) * 100.0), 4),
        "max_drawdown_pct_equal_1x": round(float(drawdown.min() * 100.0), 4),
        "profit_factor_sum_pct": round(float(gross_profit / abs(gross_loss)), 4) if gross_loss < 0 else 999.0,
        "exit_reason_counts": trades["exit_reason"].value_counts().to_dict(),
    }


def _top_candidate_keys(scored: pd.DataFrame, *, score_col: str, top_k: int) -> List[Tuple[str, str]]:
    if scored.empty:
        return []
    ranked = scored.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True])
    top = ranked.groupby("trade_date", as_index=False).head(int(top_k))
    return [(str(row["symbol"]), str(row["trade_date"])) for _, row in top.iterrows()]


def _mfe_bucket_summary(picks: pd.DataFrame, score_col: str, top_k: int) -> Dict[str, Any]:
    ranked = picks.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True])
    top = ranked.groupby("trade_date", as_index=False).head(int(top_k)).copy()
    if top.empty:
        return {"top_k": int(top_k), "picks": 0}
    mfe = pd.to_numeric(top["max_runup_22d_pct"], errors="coerce").fillna(0.0)
    close_ret = pd.to_numeric(top["close_return_22d_pct"], errors="coerce").fillna(0.0)
    return {
        "top_k": int(top_k),
        "picks": int(len(top)),
        "mfe_lt_0_rate": round(float((mfe < 0).mean()), 4),
        "mfe_0_5_rate": round(float(((mfe >= 0) & (mfe < 5)).mean()), 4),
        "mfe_5_10_rate": round(float(((mfe >= 5) & (mfe < 10)).mean()), 4),
        "mfe_10_15_rate": round(float(((mfe >= 10) & (mfe < 15)).mean()), 4),
        "mfe_15_20_rate": round(float(((mfe >= 15) & (mfe < 20)).mean()), 4),
        "mfe_ge_20_rate": round(float((mfe >= 20).mean()), 4),
        "miss15_avg_close22_return_pct": round(float(close_ret[mfe < 15].mean()), 4) if (mfe < 15).any() else 0.0,
        "miss15_median_close22_return_pct": round(float(close_ret[mfe < 15].median()), 4) if (mfe < 15).any() else 0.0,
        "miss15_avg_mdd_pct": round(float(pd.to_numeric(top.loc[mfe < 15, "max_drawdown_22d_pct"], errors="coerce").mean()), 4)
        if (mfe < 15).any()
        else 0.0,
        "miss15_worst_mdd_pct": round(float(pd.to_numeric(top.loc[mfe < 15, "max_drawdown_22d_pct"], errors="coerce").min()), 4)
        if (mfe < 15).any()
        else 0.0,
    }


def _evaluate_exit_policies(
    scored: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    config: OpportunityConfig,
    score_col: str = "final_score",
    top_ks: Sequence[int] = (1, 3, 5),
    path_map: Optional[Dict[Tuple[str, str], pd.DataFrame]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if path_map is None:
        keys = _top_candidate_keys(scored, score_col=score_col, top_k=max(top_ks))
        path_map = _future_path_map(atomic_panel, config, keys=keys)
    trades: List[Dict[str, Any]] = []
    ranked = scored.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True]).copy()
    for top_k in top_ks:
        top = ranked.groupby("trade_date", as_index=False).head(int(top_k)).copy()
        for policy in EXIT_POLICIES:
            for _, row in top.iterrows():
                key = (str(row["symbol"]), str(row["trade_date"]))
                future = path_map.get(key)
                if future is None:
                    continue
                sim = _simulate_exit_policy(future, policy, config)
                trades.append(
                    {
                        "policy": policy.name,
                        "top_k": int(top_k),
                        "trade_date": str(row["trade_date"]),
                        "symbol": str(row["symbol"]),
                        score_col: round(_to_float(row.get(score_col)), 6),
                        "max_runup_22d_pct": round(_to_float(row.get("max_runup_22d_pct")), 4),
                        "mdd_to_mfe_pct": round(_to_float(row.get("mdd_to_mfe_pct")), 4),
                        "max_drawdown_22d_pct": round(_to_float(row.get("max_drawdown_22d_pct")), 4),
                        "close_return_22d_pct": round(_to_float(row.get("close_return_22d_pct")), 4),
                        **sim,
                    }
                )
    trades_df = pd.DataFrame(trades)
    summary_rows: List[Dict[str, Any]] = []
    if not trades_df.empty:
        for (policy_name, top_k), group in trades_df.groupby(["policy", "top_k"], sort=True):
            summary_rows.append(_trade_summary(group.sort_values(["trade_date", "symbol"]), str(policy_name), int(top_k)))
    bucket_rows = [_mfe_bucket_summary(scored, score_col, k) for k in top_ks]
    return trades_df, pd.DataFrame(summary_rows), pd.DataFrame(bucket_rows)


def _build_holding_training_samples(
    entries: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    feature_panel: pd.DataFrame,
    config: OpportunityConfig,
    *,
    score_col: str = "final_score",
    top_k: int = 2,
) -> pd.DataFrame:
    feature_lookup = feature_panel.set_index(["symbol", "trade_date"], drop=False)
    ranked = entries.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True])
    top = ranked.groupby("trade_date", as_index=False).head(int(top_k)).copy()
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in top.iterrows()]
    path_map = _future_path_map(atomic_panel, config, keys=keys)
    rows: List[Dict[str, Any]] = []
    for _, entry_row in top.iterrows():
        symbol = str(entry_row["symbol"])
        signal_date = str(entry_row["trade_date"])
        future = path_map.get((symbol, signal_date))
        if future is None or future.empty:
            continue
        gross_entry = _to_float(future.iloc[0].get("open"))
        if gross_entry <= 0:
            continue
        peak_high = gross_entry
        trough_low = gross_entry
        cum_amount = 0.0
        cum_main = 0.0
        cum_super = 0.0
        close_hist: List[float] = []
        main_hist: List[float] = []
        super_hist: List[float] = []
        amount_hist: List[float] = []
        for offset, day in enumerate(future.itertuples(index=False), start=1):
            trade_date = str(getattr(day, "trade_date"))
            open_p = _to_float(getattr(day, "open", 0.0))
            high_p = _to_float(getattr(day, "high", 0.0))
            low_p = _to_float(getattr(day, "low", 0.0))
            close_p = _to_float(getattr(day, "atomic_close", 0.0))
            amount = _to_float(getattr(day, "total_amount", 0.0))
            main_net = _to_float(getattr(day, "l2_main_net_amount", 0.0))
            super_net = _to_float(getattr(day, "l2_super_net_amount", 0.0))
            if close_p <= 0 or high_p <= 0 or low_p <= 0:
                continue
            peak_high = max(peak_high, high_p)
            trough_low = min(trough_low, low_p)
            cum_amount += amount
            cum_main += main_net
            cum_super += super_net
            close_hist.append(close_p)
            main_hist.append(main_net)
            super_hist.append(super_net)
            amount_hist.append(amount)
            if offset >= int(config.horizon_days):
                break
            remaining = future.iloc[offset : int(config.horizon_days)]
            if remaining.empty:
                continue
            next_open = _to_float(remaining.iloc[0].get("open"), close_p)
            future_high = float(remaining["high"].astype(float).max())
            future_low = float(remaining["low"].astype(float).min())
            future_close = _to_float(remaining.iloc[-1].get("atomic_close"), close_p)
            future_best_return = (future_high / close_p - 1.0) * 100.0 if close_p > 0 else 0.0
            future_dd_from_close = (future_low / close_p - 1.0) * 100.0 if close_p > 0 else 0.0
            hold_value = future_best_return - max(0.0, -future_dd_from_close - 6.0) * 0.8
            sell_next_return = (next_open / close_p - 1.0) * 100.0 if close_p > 0 else 0.0
            label_keep = int(hold_value >= max(3.0, sell_next_return + 2.0))
            label_exit = int(hold_value <= 0.5 or future_close / close_p - 1.0 <= -0.06)
            frow: Dict[str, Any] = {}
            if (symbol, trade_date) in feature_lookup.index:
                rec = feature_lookup.loc[(symbol, trade_date)]
                if isinstance(rec, pd.DataFrame):
                    rec = rec.iloc[0]
                for col in HOLD_FEATURES:
                    if col in rec:
                        frow[col] = _to_float(rec.get(col))
            prev_close = close_hist[-2] if len(close_hist) >= 2 else gross_entry
            return_3 = (close_p / close_hist[-4] - 1.0) * 100.0 if len(close_hist) >= 4 and close_hist[-4] > 0 else 0.0
            return_5 = (close_p / close_hist[-6] - 1.0) * 100.0 if len(close_hist) >= 6 and close_hist[-6] > 0 else 0.0
            amount_3 = sum(amount_hist[-3:])
            main_3 = sum(main_hist[-3:])
            super_3 = sum(super_hist[-3:])
            frow.update(
                {
                    "symbol": symbol,
                    "signal_date": signal_date,
                    "trade_date": trade_date,
                    "holding_days": int(offset),
                    "gross_entry_price": round(gross_entry, 4),
                    "close": round(close_p, 4),
                    "unrealized_close_return_pct": (close_p / gross_entry - 1.0) * 100.0,
                    "max_runup_so_far_pct": (peak_high / gross_entry - 1.0) * 100.0,
                    "drawdown_from_peak_pct": (close_p / peak_high - 1.0) * 100.0 if peak_high > 0 else 0.0,
                    "max_drawdown_so_far_pct": (trough_low / gross_entry - 1.0) * 100.0,
                    "day_return_pct": (close_p / prev_close - 1.0) * 100.0 if prev_close > 0 else 0.0,
                    "return_3d_from_hold_pct": return_3,
                    "return_5d_from_hold_pct": return_5,
                    "main_net_3d_hold_ratio": main_3 / amount_3 if amount_3 else 0.0,
                    "super_net_3d_hold_ratio": super_3 / amount_3 if amount_3 else 0.0,
                    "main_net_cum_hold_ratio": cum_main / cum_amount if cum_amount else 0.0,
                    "super_net_cum_hold_ratio": cum_super / cum_amount if cum_amount else 0.0,
                    "future_best_return_from_close_pct": round(future_best_return, 4),
                    "future_dd_from_close_pct": round(future_dd_from_close, 4),
                    "label_keep": label_keep,
                    "label_exit": label_exit,
                    "hold_value": round(float(hold_value), 4),
                }
            )
            rows.append(frow)
    samples = pd.DataFrame(rows)
    if samples.empty:
        return samples
    for col in HOLD_FEATURES + ["label_keep", "label_exit", "hold_value"]:
        if col in samples.columns:
            samples[col] = pd.to_numeric(samples[col], errors="coerce").fillna(0.0)
    return samples


def _fit_holding_model(samples: pd.DataFrame, config: OpportunityConfig) -> Tuple[Pipeline, List[str]]:
    if samples.empty:
        raise RuntimeError("No holding samples were built")
    feature_cols = [col for col in HOLD_FEATURES if col in samples.columns]
    if not feature_cols:
        raise RuntimeError("No holding feature columns are available")
    X = samples[feature_cols]
    y = pd.to_numeric(samples["hold_value"], errors="coerce").fillna(0.0)
    weight = 1.0 + pd.to_numeric(samples["label_exit"], errors="coerce").fillna(0.0) * 0.7
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.05,
        max_iter=180,
        max_leaf_nodes=23,
        min_samples_leaf=35,
        l2_regularization=0.08,
        random_state=int(config.random_state) + 17,
    )
    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )
    pipe.fit(X, y, model__sample_weight=weight)
    return pipe, feature_cols


def _simulate_holding_model_trade(
    future: pd.DataFrame,
    feature_lookup: pd.DataFrame,
    hold_model: Pipeline,
    hold_features: Sequence[str],
    config: OpportunityConfig,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    if future.empty:
        return {"exit_reason": "no_future_path", "net_return_pct": 0.0, "holding_days": 0}
    gross_entry = _to_float(future.iloc[0].get("open"))
    if gross_entry <= 0:
        return {"exit_reason": "bad_entry_price", "net_return_pct": 0.0, "holding_days": 0}
    entry_price = _apply_buy_cost(gross_entry, config)
    peak_high = gross_entry
    trough_low = gross_entry
    cum_amount = 0.0
    cum_main = 0.0
    cum_super = 0.0
    close_hist: List[float] = []
    main_hist: List[float] = []
    super_hist: List[float] = []
    amount_hist: List[float] = []
    pending_exit_reason: Optional[str] = None
    pending_exit_day: Optional[str] = None
    exit_price = _to_float(future.iloc[-1].get("atomic_close"))
    exit_date = str(future.iloc[-1]["trade_date"])
    exit_reason = "time_exit_day22"
    holding_days = int(len(future))
    max_runup = 0.0
    max_drawdown = 0.0
    target_profit = policy.get("target_profit_pct")
    hard_stop = policy.get("hard_stop_pct")
    min_hold_days = int(policy.get("min_hold_days", 2))
    max_holding_days = int(policy.get("max_holding_days", 22))
    exit_threshold = float(policy.get("exit_threshold", 2.0))

    for offset, day in enumerate(future.itertuples(index=False), start=1):
        trade_date = str(getattr(day, "trade_date"))
        open_p = _to_float(getattr(day, "open", 0.0))
        high_p = _to_float(getattr(day, "high", 0.0))
        low_p = _to_float(getattr(day, "low", 0.0))
        close_p = _to_float(getattr(day, "atomic_close", 0.0))
        amount = _to_float(getattr(day, "total_amount", 0.0))
        main_net = _to_float(getattr(day, "l2_main_net_amount", 0.0))
        super_net = _to_float(getattr(day, "l2_super_net_amount", 0.0))
        if pending_exit_reason is not None and offset > 1:
            exit_price = open_p if open_p > 0 else close_p
            exit_date = trade_date
            exit_reason = pending_exit_reason
            holding_days = offset
            break
        if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
            continue
        peak_high = max(peak_high, high_p)
        trough_low = min(trough_low, low_p)
        max_runup = max(max_runup, (high_p / gross_entry - 1.0) * 100.0)
        max_drawdown = min(max_drawdown, (low_p / gross_entry - 1.0) * 100.0)
        cum_amount += amount
        cum_main += main_net
        cum_super += super_net
        close_hist.append(close_p)
        main_hist.append(main_net)
        super_hist.append(super_net)
        amount_hist.append(amount)

        # A-share T+1: shares bought at today's open cannot be sold intraday on
        # the entry day. Intraday take-profit/stop checks start from holding day 2.
        if offset >= 2 and target_profit is not None and high_p >= gross_entry * (1.0 + float(target_profit) / 100.0):
            exit_price = gross_entry * (1.0 + float(target_profit) / 100.0)
            if open_p > exit_price:
                exit_price = open_p
            exit_date = trade_date
            exit_reason = "take_profit_intraday"
            holding_days = offset
            break
        if offset >= 2 and hard_stop is not None and low_p <= gross_entry * (1.0 + float(hard_stop) / 100.0):
            exit_price = gross_entry * (1.0 + float(hard_stop) / 100.0)
            if open_p < exit_price:
                exit_price = open_p
            exit_date = trade_date
            exit_reason = "hard_stop_intraday"
            holding_days = offset
            break
        if offset >= max_holding_days:
            exit_price = close_p
            exit_date = trade_date
            exit_reason = "time_exit"
            holding_days = offset
            break
        if offset < min_hold_days:
            continue

        row_data: Dict[str, Any] = {}
        if (str(getattr(day, "symbol")), trade_date) in feature_lookup.index:
            rec = feature_lookup.loc[(str(getattr(day, "symbol")), trade_date)]
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            for col in hold_features:
                if col in rec:
                    row_data[col] = _to_float(rec.get(col))
        prev_close = close_hist[-2] if len(close_hist) >= 2 else gross_entry
        amount_3 = sum(amount_hist[-3:])
        row_data.update(
            {
                "holding_days": int(offset),
                "unrealized_close_return_pct": (close_p / gross_entry - 1.0) * 100.0,
                "max_runup_so_far_pct": (peak_high / gross_entry - 1.0) * 100.0,
                "drawdown_from_peak_pct": (close_p / peak_high - 1.0) * 100.0 if peak_high else 0.0,
                "max_drawdown_so_far_pct": (trough_low / gross_entry - 1.0) * 100.0,
                "day_return_pct": (close_p / prev_close - 1.0) * 100.0 if prev_close else 0.0,
                "return_3d_from_hold_pct": (close_p / close_hist[-4] - 1.0) * 100.0
                if len(close_hist) >= 4 and close_hist[-4] > 0
                else 0.0,
                "return_5d_from_hold_pct": (close_p / close_hist[-6] - 1.0) * 100.0
                if len(close_hist) >= 6 and close_hist[-6] > 0
                else 0.0,
                "main_net_3d_hold_ratio": sum(main_hist[-3:]) / amount_3 if amount_3 else 0.0,
                "super_net_3d_hold_ratio": sum(super_hist[-3:]) / amount_3 if amount_3 else 0.0,
                "main_net_cum_hold_ratio": cum_main / cum_amount if cum_amount else 0.0,
                "super_net_cum_hold_ratio": cum_super / cum_amount if cum_amount else 0.0,
            }
        )
        x = pd.DataFrame([{col: row_data.get(col, 0.0) for col in hold_features}])
        hold_value_pred = float(hold_model.predict(x)[0])
        if hold_value_pred < exit_threshold:
            pending_exit_reason = "hold_model_exit_next_open"
            pending_exit_day = trade_date

    net_exit = _apply_sell_cost(exit_price, config)
    return {
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "gross_entry_price": round(gross_entry, 4),
        "gross_exit_price": round(float(exit_price), 4),
        "net_return_pct": round(float((net_exit / entry_price - 1.0) * 100.0), 4),
        "gross_return_pct": round(float((exit_price / gross_entry - 1.0) * 100.0), 4),
        "holding_days": int(holding_days),
        "max_runup_before_exit_pct": round(float(max_runup), 4),
        "max_drawdown_before_exit_pct": round(float(max_drawdown), 4),
        "pending_exit_day": pending_exit_day,
    }


def _simulate_portfolio(
    scored: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    feature_panel: pd.DataFrame,
    hold_model: Pipeline,
    hold_features: Sequence[str],
    config: OpportunityConfig,
    *,
    mode: str,
    policy: Dict[str, Any],
    initial_capital: float = 1_000_000.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    trade_dates = sorted(str(d) for d in scored["trade_date"].unique())
    if mode == "top1":
        keys = _top_candidate_keys(scored, score_col="final_score", top_k=1)
    else:
        keys = _top_candidate_keys(scored, score_col="final_score", top_k=2)
    path_map = _future_path_map(atomic_panel, config, keys=keys)
    feature_lookup = feature_panel.set_index(["symbol", "trade_date"], drop=False)
    price_lookup = atomic_panel.set_index(["symbol", "trade_date"], drop=False)
    entry_orders: Dict[str, List[Dict[str, Any]]] = {}
    skipped_orders = 0

    def _record_at(symbol: str, trade_date: str) -> Optional[pd.Series]:
        try:
            rec = price_lookup.loc[(symbol, trade_date)]
        except KeyError:
            return None
        if isinstance(rec, pd.DataFrame):
            rec = rec.iloc[0]
        return rec

    def _mark_position(pos: Dict[str, Any], trade_date: str, price_col: str = "atomic_close") -> float:
        rec = _record_at(str(pos["symbol"]), trade_date)
        if rec is None:
            return float(pos.get("cost_cash", 0.0))
        price = _to_float(rec.get(price_col), 0.0)
        if price <= 0 and price_col != "atomic_close":
            price = _to_float(rec.get("atomic_close"), 0.0)
        if price <= 0:
            return float(pos.get("cost_cash", 0.0))
        return float(pos["shares"]) * _apply_sell_cost(price, config)

    def _exit_phase(exit_reason: str) -> str:
        return "open" if str(exit_reason) == "hold_model_exit_next_open" else "after_open"

    min_position_cash = max(20_000.0, initial_capital * 0.02)
    for trade_date in trade_dates:
        day = scored[scored["trade_date"] == trade_date].sort_values(["final_score", "symbol"], ascending=[False, True]).copy()
        if day.empty:
            continue
        if mode == "top1":
            entries = day.head(1).copy()
            weights = [0.80]
        elif mode == "top1_top2_conditional":
            entries = day.head(2).copy()
            if len(entries) >= 2:
                top1_score = _to_float(entries.iloc[0].get("final_score"))
                top2_score = _to_float(entries.iloc[1].get("final_score"))
                if top2_score < top1_score - 6.0:
                    entries = entries.head(1)
                    weights = [0.70]
                else:
                    weights = [0.55, 0.35]
            else:
                weights = [0.70]
        else:
            raise ValueError(f"unknown portfolio mode: {mode}")
        for idx, (_, row) in enumerate(entries.iterrows()):
            symbol = str(row["symbol"])
            future = path_map.get((symbol, trade_date))
            if future is None or future.empty:
                skipped_orders += 1
                continue
            entry_gap = _to_float(row.get("entry_gap_pct"))
            if _to_float(row.get("entry_locked_limit_up")) > 0 or entry_gap > config.max_open_gap_up_pct or entry_gap < config.max_open_gap_down_pct:
                skipped_orders += 1
                continue
            sim = _simulate_holding_model_trade(future, feature_lookup, hold_model, hold_features, config, policy)
            gross_entry = _to_float(sim.get("gross_entry_price"))
            gross_exit = _to_float(sim.get("gross_exit_price"))
            exit_date = str(sim.get("exit_date", ""))
            if gross_entry <= 0 or gross_exit <= 0 or not exit_date:
                skipped_orders += 1
                continue
            entry_date = str(future.iloc[0]["trade_date"])
            weight = weights[min(idx, len(weights) - 1)]
            order = {
                "mode": mode,
                "policy": str(policy["name"]),
                "trade_date": trade_date,
                "entry_date": entry_date,
                "symbol": symbol,
                "weight": float(weight),
                "final_score": round(_to_float(row.get("final_score")), 4),
                "max_runup_22d_pct": round(_to_float(row.get("max_runup_22d_pct")), 4),
                "gross_entry_price": gross_entry,
                "gross_exit_price": gross_exit,
                "net_entry_price": _apply_buy_cost(gross_entry, config),
                "net_exit_price": _apply_sell_cost(gross_exit, config),
                **sim,
            }
            entry_orders.setdefault(entry_date, []).append(order)

    calendar_dates = sorted(
        set(str(d) for d in atomic_panel["trade_date"].unique())
        & (
            set(entry_orders.keys())
            | {str(order["exit_date"]) for orders in entry_orders.values() for order in orders}
            | set(d for d in trade_dates)
        )
    )
    if not calendar_dates:
        return pd.DataFrame(), {"mode": mode, "policy": str(policy["name"]), "trades": 0}

    min_entry_date = min(entry_orders.keys()) if entry_orders else min(calendar_dates)
    max_exit_date = max([str(order["exit_date"]) for orders in entry_orders.values() for order in orders] or [max(calendar_dates)])
    all_atomic_dates = sorted(str(d) for d in atomic_panel["trade_date"].unique())
    calendar_dates = [d for d in all_atomic_dates if min_entry_date <= d <= max_exit_date]

    trades: List[Dict[str, Any]] = []
    daily_curve: List[Dict[str, Any]] = []
    cash = float(initial_capital)
    positions: List[Dict[str, Any]] = []

    def _close_position(pos: Dict[str, Any], trade_date: str, mark_col: str) -> None:
        nonlocal cash
        sale_cash = float(pos["shares"]) * float(pos["net_exit_price"])
        cash += sale_cash
        cost_cash = float(pos["cost_cash"])
        pnl = sale_cash - cost_cash
        open_value = sum(_mark_position(p, trade_date, mark_col) for p in positions if p is not pos)
        record = dict(pos["order"])
        record.update(
            {
                "shares": int(pos["shares"]),
                "position_cash": round(cost_cash, 2),
                "pnl_cash": round(pnl, 2),
                "equity_after": round(cash + open_value, 2),
                "net_return_pct": round((pnl / cost_cash) * 100.0, 4) if cost_cash else 0.0,
            }
        )
        trades.append(record)

    for current_date in calendar_dates:
        still_open: List[Dict[str, Any]] = []
        for pos in positions:
            if str(pos["exit_date"]) == current_date and pos["exit_phase"] == "open":
                _close_position(pos, current_date, "open")
            else:
                still_open.append(pos)
        positions = still_open

        equity_for_sizing = cash + sum(_mark_position(pos, current_date, "open") for pos in positions)
        for order in entry_orders.get(current_date, []):
            if any(str(pos["symbol"]) == str(order["symbol"]) for pos in positions):
                skipped_orders += 1
                continue
            budget = min(cash, max(0.0, equity_for_sizing * float(order["weight"])))
            if budget < min_position_cash:
                skipped_orders += 1
                continue
            shares = math.floor(budget / float(order["net_entry_price"]) / 100.0) * 100
            if shares < 100:
                skipped_orders += 1
                continue
            cost_cash = float(shares) * float(order["net_entry_price"])
            if cost_cash > cash + 1e-6:
                skipped_orders += 1
                continue
            cash -= cost_cash
            positions.append(
                {
                    "symbol": str(order["symbol"]),
                    "shares": int(shares),
                    "cost_cash": cost_cash,
                    "exit_date": str(order["exit_date"]),
                    "exit_phase": _exit_phase(str(order["exit_reason"])),
                    "net_exit_price": float(order["net_exit_price"]),
                    "order": order,
                }
            )

        still_open = []
        for pos in positions:
            if str(pos["exit_date"]) == current_date and pos["exit_phase"] != "open":
                _close_position(pos, current_date, "atomic_close")
            else:
                still_open.append(pos)
        positions = still_open
        end_equity = cash + sum(_mark_position(pos, current_date, "atomic_close") for pos in positions)
        invested_cash = sum(float(pos["cost_cash"]) for pos in positions)
        daily_curve.append(
            {
                "trade_date": current_date,
                "equity": round(end_equity, 2),
                "cash": round(cash, 2),
                "open_positions": int(len(positions)),
                "invested_cash": round(invested_cash, 2),
            }
        )

    trades_df = pd.DataFrame(trades)
    curve_df = pd.DataFrame(daily_curve)
    if trades_df.empty or curve_df.empty:
        return trades_df, {"mode": mode, "policy": str(policy["name"]), "trades": 0, "skipped_orders": int(skipped_orders)}
    final_equity = float(curve_df["equity"].iloc[-1])
    equity_curve = pd.Series([float(initial_capital)] + curve_df["equity"].astype(float).tolist())
    peak = equity_curve.cummax()
    dd = equity_curve / peak - 1.0
    returns = trades_df["net_return_pct"].astype(float)
    summary = {
        "mode": mode,
        "policy": str(policy["name"]),
        "trades": int(len(trades_df)),
        "signal_days": int(trades_df["trade_date"].nunique()),
        "skipped_orders": int(skipped_orders),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(float((final_equity / initial_capital - 1.0) * 100.0), 4),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 4),
        "avg_trade_net_return_pct": round(float(returns.mean()), 4),
        "median_trade_net_return_pct": round(float(returns.median()), 4),
        "win_rate": round(float((returns > 0).mean()), 4),
        "avg_holding_days": round(float(trades_df["holding_days"].astype(float).mean()), 2),
        "max_open_positions": int(curve_df["open_positions"].max()),
        "avg_cash_pct": round(float((curve_df["cash"].astype(float) / curve_df["equity"].replace(0, np.nan).astype(float)).mean() * 100.0), 4),
        "exit_reason_counts": trades_df["exit_reason"].value_counts().to_dict(),
    }
    return trades_df, summary


def _make_latest_candidates(panel: pd.DataFrame, model: Pipeline, feature_cols: Sequence[str], config: OpportunityConfig) -> pd.DataFrame:
    latest_date = str(panel["trade_date"].max())
    latest = panel[panel["trade_date"] == latest_date].copy()
    latest = latest[latest["risk_flag_type"].fillna("normal").eq("normal")].copy()
    latest = latest[pd.to_numeric(latest["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_signal_amount)].copy()
    latest = latest[pd.to_numeric(latest["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_signal_return_20d_pct)].copy()
    latest = latest[pd.to_numeric(latest["distribution_score"], errors="coerce").fillna(0.0) <= float(config.max_signal_distribution_score)].copy()
    if latest.empty:
        return latest
    missing = [col for col in feature_cols if col not in latest.columns]
    for col in missing:
        latest[col] = 0.0
    latest["model_score"] = model.predict(latest[list(feature_cols)])
    latest["rule_score"] = _score_rule_baseline(latest)
    latest["final_score"] = 0.78 * latest["model_score"] + 0.22 * latest["rule_score"]
    latest["operability_penalty"] = (
        latest.get("signal_locked_limit_up_like", 0).astype(float) * 24.0
        + latest.get("signal_limit_up_like", 0).astype(float) * 9.0
        + np.clip((latest["return_20d_pct"].astype(float) - 70.0) / 25.0, 0.0, 1.0) * 7.0
        + np.clip((latest["distribution_score"].astype(float) - 65.0) / 20.0, 0.0, 1.0) * 8.0
    )
    latest["action_score"] = latest["final_score"] - latest["operability_penalty"]
    latest["action_status"] = np.select(
        [
            latest.get("signal_locked_limit_up_like", 0).astype(float) > 0,
            latest.get("signal_limit_up_like", 0).astype(float) > 0,
            latest["return_20d_pct"].astype(float) >= 70.0,
            latest["distribution_score"].astype(float) >= 65.0,
        ],
        [
            "watch_only_locked_limit",
            "conditional_limit_up_signal",
            "conditional_overheated",
            "conditional_distribution_risk",
        ],
        default="actionable",
    )
    latest["tomorrow_buy_rule"] = "次日开盘高开不超过6.8%且不接近涨停才买"
    latest["risk_note"] = np.select(
        [
            latest.get("signal_locked_limit_up_like", 0).astype(float) > 0,
            latest.get("signal_limit_up_like", 0).astype(float) > 0,
            latest["hot_theme_is_climax_hot"].astype(float) > 0,
            latest["return_20d_pct"].astype(float) >= 70.0,
        ],
        [
            "信号日近似一字涨停，次日大概率难买或高开失真",
            "信号日涨停，次日高开/接力风险高",
            "热点高潮期，防接盘",
            "20日涨幅过热，次日只接受低高开确认",
        ],
        default="",
    )
    keep = [
        "trade_date",
        "symbol",
        "name",
        "action_score",
        "final_score",
        "model_score",
        "rule_score",
        "operability_penalty",
        "action_status",
        "close",
        "daily_return_pct",
        "return_5d_pct",
        "return_20d_pct",
        "total_amount",
        "breakout_score",
        "stealth_score",
        "distribution_score",
        "l2_main_net_ratio",
        "l2_super_net_ratio",
        "active_buy_strength",
        "price_position_20d",
        "hot_theme_best_rank",
        "hot_theme_score",
        "hot_theme_is_climax_hot",
        "signal_is_limit_up_close",
        "signal_limit_up_like",
        "signal_locked_limit_up_like",
        "tomorrow_buy_rule",
        "risk_note",
    ]
    keep = [col for col in keep if col in latest.columns]
    return latest.sort_values(["action_score", "symbol"], ascending=[False, True])[keep].head(80)


def train_command(args: argparse.Namespace) -> None:
    config = OpportunityConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start=args.validation_start,
        validation_end=args.validation_end,
        horizon_days=int(args.horizon_days),
    )
    atomic_db = Path(args.atomic_db)
    selection_db = Path(args.selection_db)
    heat_db = Path(args.heat_db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    data, panel = build_dataset(config, atomic_db, selection_db, heat_db)
    if data.empty:
        raise RuntimeError("No labeled opportunity dataset was built")
    feature_cols = available_feature_columns(data, include_orderbook=False)
    if not feature_cols:
        raise RuntimeError("No feature columns are available")

    train = data[pd.to_datetime(data["label_end_date"]) < pd.to_datetime(str(config.validation_start))].copy()
    valid = data[data["trade_date"] >= str(config.validation_start)].copy()
    if config.validation_end:
        valid = valid[valid["trade_date"] <= str(config.validation_end)].copy()
    train_filtered = _apply_historical_entry_filter(train, config)
    valid_filtered = _apply_historical_entry_filter(valid, config)
    if train_filtered.empty or valid_filtered.empty:
        raise RuntimeError("Train/validation split is empty after entry filters")

    model = _fit_model(train_filtered, feature_cols, config)
    for part in [train_filtered, valid_filtered]:
        part["model_score"] = model.predict(part[feature_cols])
        part["rule_score"] = _score_rule_baseline(part)
        part["final_score"] = 0.78 * part["model_score"] + 0.22 * part["rule_score"]

    valid_eval = _evaluate_topk(valid_filtered, "final_score")
    baseline_eval = _evaluate_topk(valid_filtered.assign(rule_score=_score_rule_baseline(valid_filtered)), "rule_score")
    atomic_for_exit = add_atomic_features(load_atomic_daily(config.start_date, config.end_date, atomic_db))
    trades_df, exit_summary_df, mfe_bucket_df = _evaluate_exit_policies(
        valid_filtered,
        atomic_for_exit,
        config,
        score_col="final_score",
        top_ks=(1, 3, 5),
    )
    hold_samples = _build_holding_training_samples(
        train_filtered,
        atomic_for_exit,
        panel,
        config,
        score_col="final_score",
        top_k=2,
    )
    hold_model, hold_feature_cols = _fit_holding_model(hold_samples, config)
    holding_portfolio_trades: List[pd.DataFrame] = []
    holding_portfolio_summary: List[Dict[str, Any]] = []
    for policy in HOLDING_MODEL_POLICIES:
        for mode in ["top1", "top1_top2_conditional"]:
            portfolio_trades, portfolio_summary = _simulate_portfolio(
                valid_filtered,
                atomic_for_exit,
                panel,
                hold_model,
                hold_feature_cols,
                config,
                mode=mode,
                policy=policy,
            )
            holding_portfolio_summary.append(portfolio_summary)
            if not portfolio_trades.empty:
                holding_portfolio_trades.append(portfolio_trades)
    holding_trades_df = pd.concat(holding_portfolio_trades, ignore_index=True) if holding_portfolio_trades else pd.DataFrame()
    holding_summary_df = pd.DataFrame(holding_portfolio_summary)
    latest_candidates = _make_latest_candidates(panel, model, feature_cols, config)

    valid_filtered.sort_values(["trade_date", "final_score"], ascending=[True, False]).groupby("trade_date").head(20).to_csv(
        out_dir / "validation_topk.csv", index=False
    )
    trades_df.to_csv(out_dir / "validation_exit_trades.csv", index=False)
    exit_summary_df.to_csv(out_dir / "validation_exit_policy_summary.csv", index=False)
    mfe_bucket_df.to_csv(out_dir / "validation_mfe_bucket_summary.csv", index=False)
    hold_samples.to_csv(out_dir / "holding_train_samples.csv.gz", index=False, compression="gzip")
    holding_trades_df.to_csv(out_dir / "holding_model_portfolio_trades.csv", index=False)
    holding_summary_df.to_csv(out_dir / "holding_model_portfolio_summary.csv", index=False)
    latest_candidates.to_csv(out_dir / "latest_candidates.csv", index=False)
    latest_candidates[latest_candidates["action_status"].eq("actionable")].head(30).to_csv(
        out_dir / "latest_actionable_candidates.csv", index=False
    )
    data[["symbol", "trade_date", "entry_date", "max_runup_22d_pct", "mdd_to_mfe_pct", "entry_gap_pct", "opportunity_score"]].to_csv(
        out_dir / "label_audit.csv.gz", index=False, compression="gzip"
    )
    feature_importance = _feature_importance_proxy(train_filtered, feature_cols, config)
    feature_importance.to_csv(out_dir / "feature_importance_proxy.csv", index=False)
    _write_model(out_dir / "model.joblib", model)
    _write_model(out_dir / "holding_model.joblib", hold_model)
    _json_dump(out_dir / "feature_columns.json", {"model_version": MODEL_VERSION, "features": feature_cols})
    _json_dump(
        out_dir / "holding_feature_columns.json",
        {"model_version": MODEL_VERSION, "features": hold_feature_cols, "policies": HOLDING_MODEL_POLICIES},
    )

    y_valid = pd.to_numeric(valid_filtered["opportunity_score"], errors="coerce").fillna(0.0)
    pred_valid = pd.to_numeric(valid_filtered["model_score"], errors="coerce").fillna(0.0)
    auc_payload: Dict[str, Any] = {}
    for threshold in [10.0, 15.0, 20.0]:
        y_bin = (pd.to_numeric(valid_filtered["max_runup_22d_pct"], errors="coerce").fillna(0.0) >= threshold).astype(int)
        if int(y_bin.nunique()) > 1:
            auc_payload[f"hit{int(threshold)}_auc"] = round(float(roc_auc_score(y_bin, pred_valid)), 4)

    summary = {
        "model_version": MODEL_VERSION,
        "config": asdict(config),
        "data": {
            "rows_labeled": int(len(data)),
            "train_rows": int(len(train_filtered)),
            "validation_rows": int(len(valid_filtered)),
            "train_dates": [str(train_filtered["trade_date"].min()), str(train_filtered["trade_date"].max())],
            "validation_dates": [str(valid_filtered["trade_date"].min()), str(valid_filtered["trade_date"].max())],
            "latest_candidate_date": str(panel["trade_date"].max()) if not panel.empty else None,
            "feature_count": int(len(feature_cols)),
            "holding_sample_rows": int(len(hold_samples)),
            "holding_feature_count": int(len(hold_feature_cols)),
            "orderbook_shadow_features_excluded": SHADOW_ORDERBOOK_FEATURES,
        },
        "metrics": {
            "validation_mae_opportunity_score": round(float(mean_absolute_error(y_valid, pred_valid)), 4),
            **auc_payload,
            "topk_model": valid_eval["summary"],
            "topk_rule_baseline": baseline_eval["summary"],
            "mfe_bucket_summary": mfe_bucket_df.to_dict(orient="records"),
            "exit_policy_summary": exit_summary_df.to_dict(orient="records"),
            "holding_model_portfolio_summary": holding_summary_df.to_dict(orient="records"),
        },
        "top_features_proxy": feature_importance.head(30).to_dict(orient="records"),
        "latest_candidates_top10": latest_candidates.head(10).to_dict(orient="records") if not latest_candidates.empty else [],
        "files": {
            "model": str(out_dir / "model.joblib"),
            "holding_model": str(out_dir / "holding_model.joblib"),
            "feature_columns": str(out_dir / "feature_columns.json"),
            "holding_feature_columns": str(out_dir / "holding_feature_columns.json"),
            "validation_topk": str(out_dir / "validation_topk.csv"),
            "validation_exit_trades": str(out_dir / "validation_exit_trades.csv"),
            "validation_exit_policy_summary": str(out_dir / "validation_exit_policy_summary.csv"),
            "validation_mfe_bucket_summary": str(out_dir / "validation_mfe_bucket_summary.csv"),
            "holding_train_samples": str(out_dir / "holding_train_samples.csv.gz"),
            "holding_model_portfolio_trades": str(out_dir / "holding_model_portfolio_trades.csv"),
            "holding_model_portfolio_summary": str(out_dir / "holding_model_portfolio_summary.csv"),
            "latest_candidates": str(out_dir / "latest_candidates.csv"),
            "latest_actionable_candidates": str(out_dir / "latest_actionable_candidates.csv"),
            "label_audit": str(out_dir / "label_audit.csv.gz"),
            "feature_importance_proxy": str(out_dir / "feature_importance_proxy.csv"),
        },
    }
    _json_dump(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:12000])


def catalog_command(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {"model_version": MODEL_VERSION, "tables": {}}
    for name, db_path, tables in [
        ("atomic", Path(args.atomic_db), ["atomic_trade_daily", "atomic_order_daily", "atomic_book_state_daily", "atomic_limit_state_daily"]),
        ("selection", Path(args.selection_db), ["selection_feature_daily", "selection_signal_daily"]),
        ("heat", Path(args.heat_db), ["fine_theme_heat_daily", "fine_theme_member_daily", "fine_theme_lifecycle_daily"]),
    ]:
        payload["tables"][name] = {}
        if not db_path.exists():
            payload["tables"][name]["exists"] = False
            continue
        with _connect_ro(db_path) as conn:
            for table in tables:
                if not _table_exists(conn, table):
                    payload["tables"][name][table] = {"exists": False}
                    continue
                cols = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                date_col = "trade_date" if "trade_date" in cols else ("date" if "date" in cols else None)
                stats: Dict[str, Any] = {"exists": True, "columns": cols}
                if date_col:
                    row = conn.execute(
                        f"SELECT min({date_col}), max({date_col}), count(*), count(distinct {date_col}) FROM {table}"
                    ).fetchone()
                    stats.update(
                        {
                            "start_date": row[0],
                            "end_date": row[1],
                            "rows": int(row[2] or 0),
                            "trade_dates": int(row[3] or 0),
                        }
                    )
                payload["tables"][name][table] = stats
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Opportunity discovery model research")
    parser.add_argument("--atomic-db", default=str(DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--heat-db", default=str(DEFAULT_HEAT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="Inspect usable source tables")
    catalog.set_defaults(func=catalog_command)

    train = sub.add_parser("train", help="Build labels, train baseline model, and write candidates")
    train.add_argument("--start-date", default="2025-01-02")
    train.add_argument("--end-date", default="2026-05-14")
    train.add_argument("--validation-start", default="2026-03-02")
    train.add_argument("--validation-end", default=None)
    train.add_argument("--horizon-days", type=int, default=22)
    train.add_argument("--out", default=str(OUT_DIR))
    train.set_defaults(func=train_command)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
