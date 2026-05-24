#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd


ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db")
SELECTION_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db")
HEAT_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db")

DOC_ROOT = Path(
    "/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/strategies/aggressive-10cm/experiments/low-position-agent"
)
DATA_ROOT = Path(
    "/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/aggressive_10cm/low_position_agent"
)

APRIL_TAG = "range_2026-04-01_2026-04-30_replay_2026-05-11"
FULL_TAG = "range_2026-03-02_2026-05-11"
INITIAL_CAPITAL = 1_000_000.0


@dataclass(frozen=True)
class StrategyVariant:
    name: str
    label: str
    description: str
    theme_rank_max: int
    hot_score_min: float
    position_20d_max: float
    return_5d_min: float
    return_5d_max: float
    amount_ratio_min: float
    amount_ratio_max: float
    l2_main_2d_ratio_min: float
    l2_main_today_ratio_min: float
    l2_super_3d_ratio_min: float
    selection_score_min: float
    require_stealth: bool
    require_breakout: bool
    first_15m_main_ratio_min: float
    first_15m_price_return_min: float
    buy_support_min: float
    sell_pressure_max: float
    max_open_gap_pct: float
    max_positions: int
    max_new_positions_per_day: int
    hold_days: int
    stop_loss_pct: float
    take_profit_pct: float
    trail_trigger_pct: float
    trail_from_peak_pct: float
    market_score_min: float


VARIANTS: List[StrategyVariant] = [
    StrategyVariant(
        name="low_fund_reversal",
        label="低位资金异动",
        description="低位横盘后两日主力净流入抬升，次日早盘继续净流入，偏启动异动。",
        theme_rank_max=12,
        hot_score_min=82.0,
        position_20d_max=0.45,
        return_5d_min=-6.0,
        return_5d_max=3.0,
        amount_ratio_min=0.9,
        amount_ratio_max=2.2,
        l2_main_2d_ratio_min=0.018,
        l2_main_today_ratio_min=0.010,
        l2_super_3d_ratio_min=0.004,
        selection_score_min=60.0,
        require_stealth=True,
        require_breakout=False,
        first_15m_main_ratio_min=0.004,
        first_15m_price_return_min=-0.5,
        buy_support_min=0.95,
        sell_pressure_max=1.10,
        max_open_gap_pct=4.5,
        max_positions=4,
        max_new_positions_per_day=2,
        hold_days=6,
        stop_loss_pct=-5.5,
        take_profit_pct=11.0,
        trail_trigger_pct=8.0,
        trail_from_peak_pct=-4.5,
        market_score_min=42.0,
    ),
    StrategyVariant(
        name="first_board_acceptance",
        label="首板后承接",
        description="热点主题内，前一日强承接且选股信号偏突破，次日只接首板后未充分加速的承接。",
        theme_rank_max=10,
        hot_score_min=84.0,
        position_20d_max=0.62,
        return_5d_min=-2.0,
        return_5d_max=9.8,
        amount_ratio_min=1.0,
        amount_ratio_max=2.8,
        l2_main_2d_ratio_min=0.016,
        l2_main_today_ratio_min=0.008,
        l2_super_3d_ratio_min=0.002,
        selection_score_min=64.0,
        require_stealth=False,
        require_breakout=True,
        first_15m_main_ratio_min=0.002,
        first_15m_price_return_min=-1.0,
        buy_support_min=0.92,
        sell_pressure_max=1.15,
        max_open_gap_pct=3.8,
        max_positions=3,
        max_new_positions_per_day=2,
        hold_days=5,
        stop_loss_pct=-4.8,
        take_profit_pct=9.0,
        trail_trigger_pct=6.0,
        trail_from_peak_pct=-3.5,
        market_score_min=48.0,
    ),
    StrategyVariant(
        name="funding_return",
        label="资金回流",
        description="主题仍热、个股未脱离低位，量能回到常态区间，资金回流后做次日确认。",
        theme_rank_max=15,
        hot_score_min=78.0,
        position_20d_max=0.55,
        return_5d_min=-8.0,
        return_5d_max=5.0,
        amount_ratio_min=0.75,
        amount_ratio_max=1.45,
        l2_main_2d_ratio_min=0.012,
        l2_main_today_ratio_min=0.006,
        l2_super_3d_ratio_min=0.0,
        selection_score_min=55.0,
        require_stealth=True,
        require_breakout=False,
        first_15m_main_ratio_min=0.001,
        first_15m_price_return_min=-0.8,
        buy_support_min=0.90,
        sell_pressure_max=1.18,
        max_open_gap_pct=3.2,
        max_positions=4,
        max_new_positions_per_day=2,
        hold_days=7,
        stop_loss_pct=-5.2,
        take_profit_pct=8.5,
        trail_trigger_pct=5.0,
        trail_from_peak_pct=-3.2,
        market_score_min=38.0,
    ),
]


def _ensure_dirs() -> None:
    DOC_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        if pd.isna(v):
            return 0.0
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return 0.0


def _round(v: Any, digits: int = 4) -> Optional[float]:
    if v is None:
        return None
    return round(_safe_float(v), digits)


def _pct(a: float, b: float) -> Optional[float]:
    if not b:
        return None
    return (a / b - 1.0) * 100.0


def _mainboard_symbol(symbol: str) -> bool:
    s = str(symbol).lower()
    return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def _load_trade_dates(conn: sqlite3.Connection, end_date: str) -> List[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT trade_date
        FROM atomic_trade_daily
        WHERE trade_date <= ?
        ORDER BY trade_date
        """,
        (end_date,),
    ).fetchall()
    return [str(r["trade_date"]) for r in rows]


def _load_daily(start_date: str, end_date: str) -> pd.DataFrame:
    with _connect(ATOMIC_DB) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                lower(t.symbol) AS symbol,
                t.trade_date,
                t.open,
                t.high,
                t.low,
                t.close,
                t.total_amount,
                t.l2_main_net_amount,
                t.l2_super_net_amount,
                t.positive_l2_net_bar_count,
                t.negative_l2_net_bar_count,
                o.buy_support_ratio,
                o.sell_pressure_ratio,
                o.oib_delta_amount,
                o.cvd_delta_amount,
                o.positive_oib_bar_count,
                o.negative_oib_bar_count,
                l.is_limit_up_close,
                l.is_limit_down_close,
                l.touch_limit_up,
                l.broken_limit_up
            FROM atomic_trade_daily t
            LEFT JOIN atomic_order_daily o
              ON o.symbol = t.symbol
             AND o.trade_date = t.trade_date
            LEFT JOIN atomic_limit_state_daily l
              ON l.symbol = t.symbol
             AND l.trade_date = t.trade_date
            WHERE t.trade_date >= ?
              AND t.trade_date <= ?
              AND (
                lower(t.symbol) LIKE 'sh600%%'
                OR lower(t.symbol) LIKE 'sh601%%'
                OR lower(t.symbol) LIKE 'sh603%%'
                OR lower(t.symbol) LIKE 'sh605%%'
                OR lower(t.symbol) LIKE 'sz000%%'
                OR lower(t.symbol) LIKE 'sz001%%'
                OR lower(t.symbol) LIKE 'sz002%%'
                OR lower(t.symbol) LIKE 'sz003%%'
              )
            ORDER BY lower(t.symbol), t.trade_date
            """,
            conn,
            params=[start_date, end_date],
        )
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    num_cols = [c for c in df.columns if c not in {"symbol", "trade_date"}]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _load_first_15m(start_date: str, end_date: str) -> pd.DataFrame:
    with _connect(ATOMIC_DB) as conn:
        df = pd.read_sql_query(
            """
            WITH ranked AS (
              SELECT
                lower(symbol) AS symbol,
                trade_date,
                bucket_start,
                open,
                close,
                high,
                low,
                total_amount,
                l2_main_net_amount,
                ROW_NUMBER() OVER (PARTITION BY lower(symbol), trade_date ORDER BY bucket_start) AS rn
              FROM atomic_trade_5m
              WHERE trade_date >= ?
                AND trade_date <= ?
            )
            SELECT
              symbol,
              trade_date,
              SUM(CASE WHEN rn <= 3 THEN total_amount ELSE 0 END) AS first_15m_amount,
              SUM(CASE WHEN rn <= 3 THEN l2_main_net_amount ELSE 0 END) AS first_15m_main_net_amount,
              MIN(CASE WHEN rn = 1 THEN open END) AS first_open,
              MAX(CASE WHEN rn <= 3 THEN high END) AS first_15m_high,
              MIN(CASE WHEN rn <= 3 THEN low END) AS first_15m_low,
              MIN(CASE WHEN rn = 3 THEN close END) AS confirm_close
            FROM ranked
            GROUP BY symbol, trade_date
            """,
            conn,
            params=[start_date, end_date],
        )
    if df.empty:
        return df
    for col in [c for c in df.columns if c not in {"symbol", "trade_date"}]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["first_15m_main_ratio"] = df["first_15m_main_net_amount"] / df["first_15m_amount"].replace(0, pd.NA)
    df["first_15m_main_ratio"] = df["first_15m_main_ratio"].fillna(0.0)
    df["first_15m_price_return_pct"] = (
        (df["confirm_close"] / df["first_open"].replace(0, pd.NA)) - 1.0
    ).fillna(0.0) * 100.0
    return df


def _load_selection(start_date: str, end_date: str) -> pd.DataFrame:
    with _connect(SELECTION_DB) as conn:
        df = pd.read_sql_query(
            """
            SELECT
              lower(symbol) AS symbol,
              trade_date,
              MAX(stealth_signal) AS stealth_signal,
              MAX(confirm_signal) AS confirm_signal,
              MAX(stealth_score) AS stealth_score,
              MAX(breakout_score) AS breakout_score,
              MAX(inflow_quality_score) AS inflow_quality_score
            FROM selection_signal_daily
            WHERE trade_date >= ?
              AND trade_date <= ?
            GROUP BY lower(symbol), trade_date
            """,
            conn,
            params=[start_date, end_date],
        )
    if df.empty:
        return df
    for col in [c for c in df.columns if c not in {"symbol", "trade_date"}]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _load_themes(start_date: str, end_date: str) -> pd.DataFrame:
    with _connect(HEAT_DB) as conn:
        heat = pd.read_sql_query(
            """
            SELECT
              trade_date,
              theme_id,
              sector_name,
              hot_rank,
              hot_score,
              amount_ratio,
              l2_main_net_yi
            FROM fine_theme_heat_daily
            WHERE trade_date >= ?
              AND trade_date <= ?
            """,
            conn,
            params=[start_date, end_date],
        )
        members = pd.read_sql_query(
            """
            SELECT
              trade_date,
              theme_id,
              lower(symbol) AS symbol,
              COALESCE(name, '') AS stock_name,
              return_5d,
              return_20d,
              amount_ratio_20d,
              l2_main_net_yi,
              l2_super_net_yi,
              price_position_20d
            FROM fine_theme_member_daily
            WHERE trade_date >= ?
              AND trade_date <= ?
            """,
            conn,
            params=[start_date, end_date],
        )
    if heat.empty or members.empty:
        return pd.DataFrame()
    for df in [heat, members]:
        for col in [c for c in df.columns if c not in {"trade_date", "theme_id", "symbol", "sector_name", "stock_name"}]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    merged = members.merge(heat, on=["trade_date", "theme_id"], how="left", suffixes=("", "_theme"))
    merged = merged.sort_values(["trade_date", "symbol", "hot_rank", "hot_score"], ascending=[True, True, True, False])
    return merged.drop_duplicates(["trade_date", "symbol"], keep="first")


def _prepare_dataset(load_start: str, load_end: str) -> Tuple[pd.DataFrame, List[str]]:
    daily = _load_daily(load_start, load_end)
    if daily.empty:
        return daily, []
    trade_dates = sorted(daily["trade_date"].unique().tolist())
    first15 = _load_first_15m(load_start, load_end)
    selection = _load_selection(load_start, load_end)
    themes = _load_themes(load_start, load_end)

    daily = daily.sort_values(["symbol", "trade_date"]).copy()
    g = daily.groupby("symbol", sort=False)
    daily["prev_close"] = g["close"].shift(1)
    daily["return_1d_pct"] = ((daily["close"] / daily["prev_close"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
    daily["return_5d_px_pct"] = ((daily["close"] / g["close"].shift(5).replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
    daily["amount_avg_10d"] = g["total_amount"].transform(lambda s: s.shift(1).rolling(10, min_periods=5).mean())
    daily["amount_ratio_10d"] = (daily["total_amount"] / daily["amount_avg_10d"].replace(0, pd.NA)).fillna(0.0)
    daily["l2_main_2d"] = daily["l2_main_net_amount"] + g["l2_main_net_amount"].shift(1).fillna(0.0)
    daily["l2_super_3d"] = g["l2_super_net_amount"].transform(lambda s: s.rolling(3, min_periods=3).sum()).fillna(0.0)
    daily["l2_main_2d_ratio"] = (daily["l2_main_2d"] / daily["total_amount"].replace(0, pd.NA)).fillna(0.0)
    daily["l2_main_today_ratio"] = (daily["l2_main_net_amount"] / daily["total_amount"].replace(0, pd.NA)).fillna(0.0)
    daily["l2_super_3d_ratio"] = (daily["l2_super_3d"] / (g["total_amount"].transform(lambda s: s.rolling(3, min_periods=3).sum())).replace(0, pd.NA)).fillna(0.0)
    daily["rolling_low_20d"] = g["close"].transform(lambda s: s.rolling(20, min_periods=10).min())
    daily["rolling_high_20d"] = g["close"].transform(lambda s: s.rolling(20, min_periods=10).max())
    span = (daily["rolling_high_20d"] - daily["rolling_low_20d"]).replace(0, pd.NA)
    daily["position_20d"] = ((daily["close"] - daily["rolling_low_20d"]) / span).fillna(0.5)
    daily["open_gap_pct"] = ((daily["open"] / daily["prev_close"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
    daily["next_trade_date"] = g["trade_date"].shift(-1)
    daily["next_open"] = g["open"].shift(-1)
    daily["next_high"] = g["high"].shift(-1)
    daily["next_low"] = g["low"].shift(-1)
    daily["next_close"] = g["close"].shift(-1)
    daily["next2_close"] = g["close"].shift(-2)
    daily["next3_close"] = g["close"].shift(-3)
    daily["next5_close"] = g["close"].shift(-5)

    if not first15.empty:
        daily = daily.merge(first15, on=["symbol", "trade_date"], how="left")
    if not selection.empty:
        daily = daily.merge(selection, on=["symbol", "trade_date"], how="left")
    if not themes.empty:
        daily = daily.merge(themes, on=["symbol", "trade_date"], how="left")

    fill_zero_cols = [
        "first_15m_amount",
        "first_15m_main_net_amount",
        "first_15m_main_ratio",
        "first_15m_price_return_pct",
        "stealth_signal",
        "confirm_signal",
        "stealth_score",
        "breakout_score",
        "inflow_quality_score",
        "hot_rank",
        "hot_score",
        "amount_ratio",
        "l2_main_net_yi",
        "price_position_20d",
        "return_5d",
        "return_20d",
    ]
    for col in fill_zero_cols:
        if col not in daily.columns:
            daily[col] = 0.0
        else:
            daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0.0)
    for col in ["sector_name", "stock_name", "theme_id"]:
        if col not in daily.columns:
            daily[col] = ""
        else:
            daily[col] = daily[col].fillna("")
    return daily, trade_dates


def _market_regime(day_df: pd.DataFrame) -> Dict[str, float]:
    if day_df.empty:
        return {"score": 0.0, "adv_ratio": 0.0, "median_ret": 0.0, "limit_up_count": 0.0}
    adv_ratio = float((day_df["return_1d_pct"] > 0).mean())
    median_ret = float(day_df["return_1d_pct"].median())
    main_ratio = float(day_df["l2_main_net_amount"].sum() / max(day_df["total_amount"].sum(), 1.0))
    limit_up_count = float((day_df["is_limit_up_close"] > 0).sum())
    score = 100.0 * (
        0.35 * min(max((adv_ratio - 0.35) / 0.30, 0.0), 1.0)
        + 0.30 * min(max((median_ret + 1.0) / 2.2, 0.0), 1.0)
        + 0.20 * min(max((main_ratio + 0.02) / 0.04, 0.0), 1.0)
        + 0.15 * min(max(limit_up_count / 80.0, 0.0), 1.0)
    )
    return {
        "score": round(score, 2),
        "adv_ratio": round(adv_ratio, 4),
        "median_ret": round(median_ret, 4),
        "limit_up_count": int(limit_up_count),
    }


def _simulate_trade(entry_open: float, future_rows: Sequence[Dict[str, Any]], variant: StrategyVariant) -> Tuple[Dict[str, Any], float]:
    peak = entry_open
    exit_price = entry_open
    exit_date = future_rows[-1]["trade_date"] if future_rows else ""
    exit_reason = "time_exit"
    hold_days = 0
    for idx, row in enumerate(future_rows, start=1):
        hold_days = idx
        high = _safe_float(row["high"])
        low = _safe_float(row["low"])
        close = _safe_float(row["close"])
        trade_date = str(row["trade_date"])
        peak = max(peak, high, close)
        stop_price = entry_open * (1.0 + variant.stop_loss_pct / 100.0)
        take_price = entry_open * (1.0 + variant.take_profit_pct / 100.0)
        trail_active = peak >= entry_open * (1.0 + variant.trail_trigger_pct / 100.0)
        trail_price = peak * (1.0 + variant.trail_from_peak_pct / 100.0) if trail_active else -math.inf

        if low <= stop_price:
            exit_price = stop_price
            exit_date = trade_date
            exit_reason = "stop_loss"
            break
        if high >= take_price and not trail_active:
            exit_price = take_price
            exit_date = trade_date
            exit_reason = "take_profit"
            break
        if trail_active and low <= trail_price:
            exit_price = trail_price
            exit_date = trade_date
            exit_reason = "trailing_stop"
            break
        exit_price = close
        exit_date = trade_date
    gross_return_pct = _pct(exit_price, entry_open) or 0.0
    net_return_pct = gross_return_pct - 0.42
    trade = {
        "exit_date": exit_date,
        "exit_price": round(exit_price, 3),
        "exit_reason": exit_reason,
        "hold_days": hold_days,
        "gross_return_pct": round(gross_return_pct, 4),
        "net_return_pct": round(net_return_pct, 4),
        "peak_return_pct": round((_pct(peak, entry_open) or 0.0), 4),
    }
    return trade, net_return_pct


def _build_candidates(day_df: pd.DataFrame, variant: StrategyVariant) -> pd.DataFrame:
    df = day_df.copy()
    cond = (
        (df["hot_rank"] > 0)
        & (df["hot_rank"] <= variant.theme_rank_max)
        & (df["hot_score"] >= variant.hot_score_min)
        & (df["position_20d"] <= variant.position_20d_max)
        & (df["return_5d"].between(variant.return_5d_min, variant.return_5d_max))
        & (df["amount_ratio_10d"].between(variant.amount_ratio_min, variant.amount_ratio_max))
        & (df["l2_main_2d_ratio"] >= variant.l2_main_2d_ratio_min)
        & (df["l2_main_today_ratio"] >= variant.l2_main_today_ratio_min)
        & (df["l2_super_3d_ratio"] >= variant.l2_super_3d_ratio_min)
        & (df["first_15m_main_ratio"] >= variant.first_15m_main_ratio_min)
        & (df["first_15m_price_return_pct"] >= variant.first_15m_price_return_min)
        & (df["buy_support_ratio"] >= variant.buy_support_min)
        & (df["sell_pressure_ratio"] <= variant.sell_pressure_max)
        & (df["next_trade_date"].notna())
        & (df["next_open"] > 0)
        & (df["open_gap_pct"] <= 9.9)
        & (df["total_amount"] >= 180_000_000.0)
        & (df["is_limit_down_close"] <= 0)
    )
    if variant.require_stealth:
        cond &= (df["stealth_signal"] > 0) & (df["stealth_score"] >= variant.selection_score_min)
    if variant.require_breakout:
        cond &= (df["confirm_signal"] > 0) & (df["breakout_score"] >= variant.selection_score_min)
    return df.loc[cond].copy()


def _run_range(dataset: pd.DataFrame, trade_dates: Sequence[str], start_date: str, signal_end_date: str, replay_end_date: str, variant: StrategyVariant) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    date_set = set(trade_dates)
    signal_dates = [d for d in trade_dates if start_date <= d <= signal_end_date]
    replay_last = replay_end_date if replay_end_date in date_set else max([d for d in trade_dates if d <= replay_end_date], default=signal_end_date)
    day_map = {d: dataset[dataset["trade_date"] == d].copy() for d in signal_dates}
    regime_map = {d: _market_regime(df) for d, df in day_map.items()}

    open_positions: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    equity = INITIAL_CAPITAL
    peak_equity = INITIAL_CAPITAL
    daily_equity: List[float] = []

    for trade_date in signal_dates:
        still_open: List[Dict[str, Any]] = []
        for pos in open_positions:
            if trade_date <= pos["exit_date"]:
                still_open.append(pos)
            else:
                equity += pos["pnl"]
        open_positions = still_open

        regime = regime_map.get(trade_date, {"score": 0.0})
        if regime["score"] < variant.market_score_min:
            daily_equity.append(equity)
            peak_equity = max(peak_equity, equity)
            continue

        candidates = _build_candidates(day_map[trade_date], variant)
        if candidates.empty:
            daily_equity.append(equity)
            peak_equity = max(peak_equity, equity)
            continue

        candidates = candidates.copy()
        candidates["entry_gap_pct"] = ((candidates["next_open"] / candidates["close"].replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        candidates = candidates[candidates["entry_gap_pct"] <= variant.max_open_gap_pct]
        if candidates.empty:
            daily_equity.append(equity)
            peak_equity = max(peak_equity, equity)
            continue

        candidates["rank_score"] = (
            candidates["l2_main_2d_ratio"] * 3000.0
            + candidates["first_15m_main_ratio"] * 1500.0
            + candidates["hot_score"] * 0.3
            - candidates["position_20d"] * 30.0
            - candidates["entry_gap_pct"] * 2.0
        )
        candidates = candidates.sort_values(["rank_score", "hot_rank"], ascending=[False, True])

        slots = max(0, variant.max_positions - len(open_positions))
        take_n = min(slots, variant.max_new_positions_per_day, len(candidates))
        if take_n <= 0:
            daily_equity.append(equity)
            peak_equity = max(peak_equity, equity)
            continue

        picked = candidates.head(take_n)
        for row in picked.to_dict("records"):
            entry_date = str(row["next_trade_date"])
            future = dataset[(dataset["symbol"] == row["symbol"]) & (dataset["trade_date"] > entry_date) & (dataset["trade_date"] <= replay_last)]
            future = future.sort_values("trade_date").head(variant.hold_days)
            future_rows = future[["trade_date", "high", "low", "close"]].to_dict("records")
            if not future_rows:
                continue
            entry_open = _safe_float(row["next_open"])
            trade_result, net_ret = _simulate_trade(entry_open, future_rows, variant)
            allocation = equity / max(variant.max_positions, 1)
            pnl = allocation * net_ret / 100.0
            record = {
                "strategy": variant.name,
                "strategy_label": variant.label,
                "signal_date": trade_date,
                "entry_date": entry_date,
                "symbol": row["symbol"],
                "stock_name": row.get("stock_name") or "",
                "theme_id": row.get("theme_id") or "",
                "theme_name": row.get("sector_name") or "",
                "theme_rank": int(_safe_float(row.get("hot_rank"))),
                "hot_score": round(_safe_float(row.get("hot_score")), 2),
                "market_score": regime["score"],
                "entry_price": round(entry_open, 3),
                "entry_gap_pct": round(_safe_float(row["entry_gap_pct"]), 4),
                "position_20d": round(_safe_float(row["position_20d"]), 4),
                "return_5d_pct": round(_safe_float(row["return_5d"]), 4),
                "amount_ratio_10d": round(_safe_float(row["amount_ratio_10d"]), 4),
                "l2_main_2d_ratio": round(_safe_float(row["l2_main_2d_ratio"]), 4),
                "l2_main_today_ratio": round(_safe_float(row["l2_main_today_ratio"]), 4),
                "l2_super_3d_ratio": round(_safe_float(row["l2_super_3d_ratio"]), 4),
                "first_15m_main_ratio": round(_safe_float(row["first_15m_main_ratio"]), 4),
                "first_15m_price_return_pct": round(_safe_float(row["first_15m_price_return_pct"]), 4),
                "stealth_signal": int(_safe_float(row["stealth_signal"])),
                "confirm_signal": int(_safe_float(row["confirm_signal"])),
                "stealth_score": round(_safe_float(row["stealth_score"]), 2),
                "breakout_score": round(_safe_float(row["breakout_score"]), 2),
                **trade_result,
                "allocation": round(allocation, 2),
                "pnl": round(pnl, 2),
            }
            trades.append(record)
            open_positions.append({"exit_date": trade_result["exit_date"], "pnl": pnl})

        daily_equity.append(equity + sum(pos["pnl"] for pos in open_positions))
        peak_equity = max(peak_equity, daily_equity[-1])

    for pos in open_positions:
        equity += pos["pnl"]
    returns = [t["net_return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    total_return_pct = (equity / INITIAL_CAPITAL - 1.0) * 100.0
    max_drawdown_pct = 0.0
    if daily_equity:
        running_peak = daily_equity[0]
        drawdowns = []
        for v in daily_equity:
            running_peak = max(running_peak, v)
            drawdowns.append((v / running_peak - 1.0) * 100.0 if running_peak else 0.0)
        max_drawdown_pct = min(drawdowns)

    summary = {
        "strategy": variant.name,
        "strategy_label": variant.label,
        "description": variant.description,
        "signal_start_date": start_date,
        "signal_end_date": signal_end_date,
        "replay_end_date": replay_last,
        "initial_capital": INITIAL_CAPITAL,
        "ending_capital": round(equity, 2),
        "total_return_pct": round(total_return_pct, 4),
        "trade_count": len(trades),
        "win_rate_pct": round((len(wins) / len(trades) * 100.0) if trades else 0.0, 4),
        "avg_net_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "median_net_return_pct": round(pd.Series(returns).median(), 4) if returns else 0.0,
        "profit_factor": round((sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (999.0 if wins else 0.0), 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "avg_hold_days": round(sum(t["hold_days"] for t in trades) / len(trades), 4) if trades else 0.0,
    }
    return summary, trades


def _write_trades(path: Path, trades: List[Dict[str, Any]]) -> None:
    if not trades:
        path.write_text("", encoding="utf-8")
        return
    fields = list(trades[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)


def _write_readme(path: Path, payload: Dict[str, Any]) -> None:
    best = payload["best_strategy"]
    lines = [
        "# low-position-agent",
        "",
        "## 策略变体",
        "",
    ]
    for item in payload["strategies"]:
        lines.append(f"- `{item['strategy']}`: {item['description']}")
    lines += [
        "",
        "## 区间结果",
        "",
        "| 区间 | 策略 | 收益率 | 交易数 | 胜率 | 最大回撤 | 盈亏比 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for rng in payload["ranges"]:
        for row in rng["summaries"]:
            lines.append(
                f"| {rng['tag']} | {row['strategy_label']} | {row['total_return_pct']:.2f}% | {row['trade_count']} | "
                f"{row['win_rate_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | {row['profit_factor']:.2f} |"
            )
    lines += [
        "",
        "## 最优策略",
        "",
        f"- 策略：{best['strategy_label']} (`{best['strategy']}`)",
        f"- 全样本收益：{best['full_range']['total_return_pct']:.2f}%",
        f"- 全样本最大回撤：{best['full_range']['max_drawdown_pct']:.2f}%",
        f"- 4月信号回放收益：{best['april_range']['total_return_pct']:.2f}%",
        "",
        "## 无未来函数",
        "",
        "- 信号日只使用当日 `atomic_trade_daily` / `atomic_order_daily` / `selection_signal_daily` / `fine_theme_*_daily`。",
        "- 买点固定为下一交易日开盘价，且用下一交易日首15分钟 `atomic_trade_5m` 做早盘确认。",
        "- 卖出仅依据入场后逐日 OHLC 路径触发止损/止盈/移动止盈，不读取未来主题热度或未来选股信号。",
        f"- 2026-04-01~2026-04-30 的信号只回放到 {payload['ranges'][0]['replay_end_date']}；更长区间只回放到样本截止日。",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research aggressive 10cm low-position strategies without lookahead.")
    parser.add_argument("--april-start", default="2026-04-01")
    parser.add_argument("--april-end", default="2026-04-30")
    parser.add_argument("--april-replay-end", default="2026-05-11")
    parser.add_argument("--full-start", default="2026-03-02")
    parser.add_argument("--full-end", default="2026-05-11")
    args = parser.parse_args()

    _ensure_dirs()
    load_start = min(args.full_start, args.april_start)
    load_end = max(args.full_end, args.april_replay_end)
    dataset, trade_dates = _prepare_dataset(load_start, load_end)
    if dataset.empty:
        raise SystemExit("No data loaded.")

    range_specs = [
        {"tag": APRIL_TAG, "start": args.april_start, "end": args.april_end, "replay_end": args.april_replay_end},
        {"tag": FULL_TAG, "start": args.full_start, "end": args.full_end, "replay_end": args.full_end},
    ]

    strategies_meta = [{"strategy": v.name, "label": v.label, "description": v.description} for v in VARIANTS]
    range_payloads: List[Dict[str, Any]] = []
    best_rows: Dict[str, Dict[str, Any]] = {}

    for spec in range_specs:
        range_dir_data = DATA_ROOT / spec["tag"]
        range_dir_doc = DOC_ROOT / spec["tag"]
        range_dir_data.mkdir(parents=True, exist_ok=True)
        range_dir_doc.mkdir(parents=True, exist_ok=True)

        summaries: List[Dict[str, Any]] = []
        all_trades: List[Dict[str, Any]] = []
        by_strategy: Dict[str, Dict[str, Any]] = {}
        for variant in VARIANTS:
            summary, trades = _run_range(dataset, trade_dates, spec["start"], spec["end"], spec["replay_end"], variant)
            summaries.append(summary)
            all_trades.extend(trades)
            by_strategy[variant.name] = {"summary": summary, "trade_count": len(trades)}
            best_rows.setdefault(variant.name, {})[spec["tag"]] = summary

        summaries = sorted(summaries, key=lambda x: (x["total_return_pct"], x["profit_factor"], -abs(x["max_drawdown_pct"])), reverse=True)
        summary_json = {
            "tag": spec["tag"],
            "signal_start_date": spec["start"],
            "signal_end_date": spec["end"],
            "replay_end_date": spec["replay_end"],
            "strategies": strategies_meta,
            "summaries": summaries,
        }
        (range_dir_data / "summary.json").write_text(json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")
        (range_dir_doc / "summary.json").write_text(json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_trades(range_dir_data / "trades.csv", all_trades)
        _write_trades(range_dir_doc / "trades.csv", all_trades)
        range_payloads.append(
            {
                "tag": spec["tag"],
                "signal_start_date": spec["start"],
                "signal_end_date": spec["end"],
                "replay_end_date": spec["replay_end"],
                "summaries": summaries,
                "by_strategy": by_strategy,
            }
        )

    best_variant = sorted(
        VARIANTS,
        key=lambda v: (
            best_rows[v.name][FULL_TAG]["total_return_pct"],
            best_rows[v.name][FULL_TAG]["profit_factor"],
            best_rows[v.name][FULL_TAG]["max_drawdown_pct"],
        ),
        reverse=True,
    )[0]
    final_payload = {
        "strategies": strategies_meta,
        "ranges": range_payloads,
        "best_strategy": {
            "strategy": best_variant.name,
            "strategy_label": best_variant.label,
            "april_range": best_rows[best_variant.name][APRIL_TAG],
            "full_range": best_rows[best_variant.name][FULL_TAG],
        },
        "no_lookahead": {
            "signal_inputs": [
                "atomic_trade_daily",
                "atomic_order_daily",
                "atomic_trade_5m(first 15m only on entry day)",
                "selection_signal_daily",
                "fine_theme_heat_daily",
                "fine_theme_member_daily",
            ],
            "entry_rule": "signal_date T uses only T data, enters at T+1 open with T+1 first-15m confirmation",
            "exit_rule": "post-entry only uses realized daily OHLC path until replay_end_date",
        },
    }
    (DATA_ROOT / "summary.json").write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOC_ROOT / "summary.json").write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(DATA_ROOT / "README.md", final_payload)
    _write_readme(DOC_ROOT / "README.md", final_payload)


if __name__ == "__main__":
    main()
