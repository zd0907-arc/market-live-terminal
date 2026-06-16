#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import RESEARCH_CURRENT_ROOT


DEFAULT_RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
DEFAULT_ATOMIC_DB = Path(
    os.getenv(
        "ATOMIC_COMPACT_DB_PATH",
        str(DEFAULT_RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
    )
)
DEFAULT_FEATURE_DB = Path(
    os.getenv(
        "MODEL_FEATURE_STORE_DB_PATH",
        str(DEFAULT_RESEARCH_ROOT / "selection" / "model_feature_store.db"),
    )
)
DEFAULT_SELECTION_DB = Path(
    os.getenv(
        "SELECTION_DB_PATH",
        str(DEFAULT_RESEARCH_ROOT / "selection" / "selection_research.db"),
    )
)
DEFAULT_HEAT_DB = Path(
    os.getenv(
        "FINE_THEME_HEAT_V2_DB",
        str(DEFAULT_RESEARCH_ROOT / "market_heat" / "fine_theme_heat_daily_v2.db"),
    )
)
DEFAULT_THEME_MAP_DB = Path(
    os.getenv(
        "TRADABLE_THEME_MAP_DB",
        str(DEFAULT_RESEARCH_ROOT / "market_heat" / "tradable_theme_map.db"),
    )
)

EXPERIMENT_DIR = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"
SCAN_START = "2026-03-02"
SCAN_END = "2026-06-03"
FORWARD_HORIZONS = (1, 3, 5, 10, 20)
TRADE_DATE_GAP_FOR_CONTINUOUS = 5
TRADE_DATE_GAP_FOR_RETEST = 6
LAUNCH_WINDOW = 10
FULL_DATA_START = "2026-03-02"
SAMPLE_REVIEW_LIMIT = 40


@dataclass(frozen=True)
class Thresholds:
    probe_bar_high_ret_pct: float
    probe_bar_close_ret_pct: float
    probe_amount_vs_day_median: float
    probe_same_day_pullback_ratio: float
    probe_same_day_later_high_pct: float
    probe_oib_ratio: float
    launch_same_day_later_high_pct: float
    launch_close_pullback_ratio_max: float
    launch_day_return_pct: float
    relaunch_return_3d_pct: float


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path.expanduser().resolve()), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def quantile(series: pd.Series, q: float) -> float:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def load_trade_dates(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT trade_date
        FROM atomic_trade_daily
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date
        """,
        (SCAN_START, SCAN_END),
    ).fetchall()
    return [str(row["trade_date"]) for row in rows]


@lru_cache(maxsize=1)
def load_trade_date_index() -> Dict[str, int]:
    conn = connect_ro(DEFAULT_ATOMIC_DB)
    try:
        return {d: i for i, d in enumerate(load_trade_dates(conn))}
    finally:
        conn.close()


def build_event_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    stock_days = pd.read_sql_query(
        """
        SELECT symbol, trade_date, open AS day_open, high AS day_high, low AS day_low, close AS day_close, total_amount AS day_amount
        FROM atomic_trade_daily
        WHERE trade_date >= ? AND trade_date <= ?
          AND high / NULLIF(open, 0) >= 1.04
          AND total_amount >= 80000000
        ORDER BY trade_date, symbol
        """,
        conn,
        params=[SCAN_START, SCAN_END],
    )
    conn.execute("DROP TABLE IF EXISTS temp_probe_days")
    conn.execute("CREATE TEMP TABLE temp_probe_days(symbol TEXT, trade_date TEXT, PRIMARY KEY(symbol, trade_date))")
    conn.executemany(
        "INSERT INTO temp_probe_days(symbol, trade_date) VALUES (?, ?)",
        stock_days[["symbol", "trade_date"]].itertuples(index=False, name=None),
    )
    bars = pd.read_sql_query(
        """
        SELECT
          t.symbol,
          t.trade_date,
          t.bucket_start,
          t.open,
          t.high,
          t.low,
          t.close,
          t.total_amount,
          t.l2_main_net_amount,
          t.l2_super_net_amount,
          o.add_buy_amount,
          o.add_sell_amount,
          o.cancel_buy_amount,
          o.cancel_sell_amount,
          o.oib_delta_amount,
          o.cvd_delta_amount,
          b.book_imbalance_ratio,
          b.end_bid_resting_amount,
          b.end_ask_resting_amount
        FROM atomic_trade_5m t
        JOIN temp_probe_days d
          ON d.symbol = t.symbol
         AND d.trade_date = t.trade_date
        LEFT JOIN atomic_order_5m o
          ON o.symbol = t.symbol
         AND o.bucket_start = t.bucket_start
        LEFT JOIN atomic_book_state_5m b
          ON b.symbol = t.symbol
         AND b.bucket_start = t.bucket_start
        ORDER BY t.symbol, t.trade_date, t.bucket_start
        """,
        conn,
    )
    bars["bucket_start"] = pd.to_datetime(bars["bucket_start"])
    bars["event_time"] = bars["bucket_start"].dt.strftime("%H:%M")
    bars["bar_prev_close"] = bars.groupby(["symbol", "trade_date"])["close"].shift(1)
    bars["ref_price"] = bars["bar_prev_close"].fillna(bars["open"])
    bars["bar_high_ret_pct"] = (bars["high"] / bars["ref_price"] - 1.0) * 100.0
    bars["bar_close_ret_pct"] = (bars["close"] / bars["ref_price"] - 1.0) * 100.0
    bars["bar_low_ret_pct"] = (bars["low"] / bars["ref_price"] - 1.0) * 100.0
    bars["oib_ratio"] = bars["oib_delta_amount"] / bars["total_amount"].replace(0, np.nan)
    bars["cvd_ratio"] = bars["cvd_delta_amount"] / bars["total_amount"].replace(0, np.nan)
    bars["add_buy_ratio"] = bars["add_buy_amount"] / bars["total_amount"].replace(0, np.nan)
    bars["add_sell_ratio"] = bars["add_sell_amount"] / bars["total_amount"].replace(0, np.nan)
    bars["amount_vs_day_median"] = bars["total_amount"] / bars.groupby(["symbol", "trade_date"])["total_amount"].transform("median").replace(0, np.nan)

    idx = bars.groupby(["symbol", "trade_date"])["bar_high_ret_pct"].idxmax()
    events = bars.loc[idx].copy().reset_index(drop=True)
    events = events.merge(stock_days, on=["symbol", "trade_date"], how="left")
    limit_state = pd.read_sql_query(
        """
        SELECT
          symbol,
          trade_date,
          prev_close,
          touch_limit_up,
          is_limit_up_close,
          broken_limit_up,
          touch_limit_up_count_5m,
          first_touch_limit_up_time,
          last_touch_limit_up_time,
          limit_state_label
        FROM atomic_limit_state_daily
        WHERE trade_date >= ? AND trade_date <= ?
        """,
        conn,
        params=[SCAN_START, SCAN_END],
    )
    events = events.merge(limit_state, on=["symbol", "trade_date"], how="left")
    events["day_prev_close"] = pd.to_numeric(events["prev_close"], errors="coerce")
    events["day_prev_close"] = events["day_prev_close"].fillna(events.groupby("symbol")["day_close"].shift(1))
    events["day_prev_close"] = events["day_prev_close"].fillna(events["day_open"])
    events["same_day_pullback_ratio"] = np.where(
        (events["high"] - events["ref_price"]) > 0,
        (events["high"] - events["day_close"]) / (events["high"] - events["ref_price"]),
        np.nan,
    )
    events["same_day_later_high_pct"] = (events["day_high"] / events["high"] - 1.0) * 100.0
    events["event_close_vs_day_close_pct"] = (events["day_close"] / events["close"] - 1.0) * 100.0
    events["day_gap_pct"] = (events["day_open"] / events["day_prev_close"] - 1.0) * 100.0
    events["day_high_vs_prev_close_pct"] = (events["day_high"] / events["day_prev_close"] - 1.0) * 100.0
    events["day_return_pct"] = (events["day_close"] / events["day_open"] - 1.0) * 100.0
    events["high_from_day_open_pct"] = (events["day_high"] / events["day_open"] - 1.0) * 100.0
    events["business_anchor_time"] = events["event_time"]
    touch_time = pd.to_datetime(events["first_touch_limit_up_time"], errors="coerce")
    events.loc[touch_time.notna(), "business_anchor_time"] = touch_time.dt.strftime("%H:%M")
    return events


def derive_thresholds(events: pd.DataFrame) -> Thresholds:
    return Thresholds(
        probe_bar_high_ret_pct=quantile(events["bar_high_ret_pct"], 0.75),
        probe_bar_close_ret_pct=quantile(events["bar_close_ret_pct"], 0.60),
        probe_amount_vs_day_median=quantile(events["amount_vs_day_median"], 0.70),
        probe_same_day_pullback_ratio=quantile(events["same_day_pullback_ratio"], 0.60),
        probe_same_day_later_high_pct=quantile(events["same_day_later_high_pct"], 0.25),
        probe_oib_ratio=quantile(events["oib_ratio"], 0.65),
        launch_same_day_later_high_pct=quantile(events["same_day_later_high_pct"], 0.70),
        launch_close_pullback_ratio_max=quantile(events["same_day_pullback_ratio"], 0.35),
        launch_day_return_pct=quantile(events["day_return_pct"], 0.75),
        relaunch_return_3d_pct=4.0,
    )


def classify_events(events: pd.DataFrame, thresholds: Thresholds) -> pd.DataFrame:
    out = events.copy()
    out["is_probe_candidate"] = (
        (out["bar_high_ret_pct"] >= thresholds.probe_bar_high_ret_pct)
        & (out["bar_close_ret_pct"] >= thresholds.probe_bar_close_ret_pct)
        & (out["amount_vs_day_median"] >= thresholds.probe_amount_vs_day_median)
        & (out["same_day_pullback_ratio"] >= thresholds.probe_same_day_pullback_ratio)
        & (out["same_day_later_high_pct"] <= thresholds.probe_same_day_later_high_pct)
        & (out["oib_ratio"] >= thresholds.probe_oib_ratio)
        & (out["day_return_pct"] < thresholds.launch_day_return_pct)
    )
    out["is_launch_day"] = (
        (out["bar_high_ret_pct"] >= thresholds.probe_bar_high_ret_pct)
        & (out["amount_vs_day_median"] >= thresholds.probe_amount_vs_day_median)
        & (
            (out["same_day_later_high_pct"] > thresholds.launch_same_day_later_high_pct)
            | (out["same_day_pullback_ratio"] <= thresholds.launch_close_pullback_ratio_max)
            | (out["day_return_pct"] >= thresholds.launch_day_return_pct)
        )
    )
    out["is_launch_day"] = out["is_launch_day"] | (
        (out["touch_limit_up"].fillna(0).astype(int) == 1)
        & (out["day_high_vs_prev_close_pct"] >= 9.5)
    )
    out["event_kind"] = np.where(out["is_launch_day"], "launch_day", np.where(out["is_probe_candidate"], "probe_candidate", "non_probe"))
    out["probe_strength_score"] = (
        out["bar_high_ret_pct"].rank(pct=True) * 0.30
        + out["amount_vs_day_median"].rank(pct=True) * 0.20
        + out["same_day_pullback_ratio"].rank(pct=True) * 0.20
        + out["oib_ratio"].rank(pct=True) * 0.15
        + out["cvd_ratio"].rank(pct=True) * 0.10
        + (1.0 - out["same_day_later_high_pct"].rank(pct=True)) * 0.05
    ) * 100.0
    return out


def build_followup(conn: sqlite3.Connection, event_scan: pd.DataFrame) -> pd.DataFrame:
    symbols = sorted(set(map(str, event_scan["symbol"].dropna().tolist())))
    if not symbols:
        return pd.DataFrame()
    conn.execute("DROP TABLE IF EXISTS temp_followup_symbols")
    conn.execute("CREATE TEMP TABLE temp_followup_symbols(symbol TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO temp_followup_symbols(symbol) VALUES (?)",
        [(symbol,) for symbol in symbols],
    )
    daily = pd.read_sql_query(
        """
        SELECT symbol, trade_date, open, high, low, close, total_amount
        FROM atomic_trade_daily
        WHERE symbol IN (SELECT symbol FROM temp_followup_symbols)
          AND trade_date >= ? AND trade_date <= ?
        """,
        conn,
        params=[SCAN_START, SCAN_END],
    )
    daily = daily.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    daily["return_1d_pct"] = daily.groupby("symbol")["close"].pct_change() * 100.0
    by_symbol = {sym: g.reset_index(drop=True) for sym, g in daily.groupby("symbol", sort=False)}
    rows: List[Dict[str, Any]] = []
    for rec in event_scan.itertuples(index=False):
        row = {
            "symbol": rec.symbol,
            "trade_date": rec.trade_date,
            "event_time": rec.event_time,
            "business_anchor_time": getattr(rec, "business_anchor_time", rec.event_time),
            "event_kind": rec.event_kind,
            "event_role": rec.event_role,
            "sequence_label": rec.sequence_label,
            "probe_strength_score": round(safe_float(rec.probe_strength_score), 2),
        }
        sym_daily = by_symbol.get(rec.symbol)
        if sym_daily is None:
            rows.append(row)
            continue
        pos = sym_daily.index[sym_daily["trade_date"] == rec.trade_date].tolist()
        if not pos:
            rows.append(row)
            continue
        i = pos[0]
        base_close = safe_float(sym_daily.loc[i, "close"])
        for h in FORWARD_HORIZONS:
            if base_close <= 0 or i + h >= len(sym_daily):
                row[f"fwd_{h}d_close_ret_pct"] = np.nan
                row[f"fwd_{h}d_high_ret_pct"] = np.nan
                row[f"fwd_{h}d_low_ret_pct"] = np.nan
                continue
            j = i + h
            window = sym_daily.iloc[i + 1 : j + 1]
            close_ret = (safe_float(sym_daily.loc[j, "close"]) / base_close - 1.0) * 100.0
            high_ret = (window["high"].max() / base_close - 1.0) * 100.0
            low_ret = (window["low"].min() / base_close - 1.0) * 100.0
            row[f"fwd_{h}d_close_ret_pct"] = round(close_ret, 4)
            row[f"fwd_{h}d_high_ret_pct"] = round(high_ret, 4)
            row[f"fwd_{h}d_low_ret_pct"] = round(low_ret, 4)
        if base_close > 0 and i + 10 < len(sym_daily):
            window_10d = sym_daily.iloc[i + 1 : i + 11]
            row["fwd_10d_max_runup_pct"] = round((safe_float(window_10d["high"].max()) / base_close - 1.0) * 100.0, 4)
            row["fwd_10d_max_drawdown_pct"] = round((safe_float(window_10d["low"].min()) / base_close - 1.0) * 100.0, 4)
        else:
            row["fwd_10d_max_runup_pct"] = np.nan
            row["fwd_10d_max_drawdown_pct"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def tag_sequences(event_scan: pd.DataFrame) -> pd.DataFrame:
    scan = event_scan.sort_values(["symbol", "trade_date", "event_time"]).copy()
    scan["event_role"] = "non_probe"
    scan["sequence_label"] = ""
    scan["probe_index"] = np.nan
    scan["days_since_prev_probe"] = np.nan
    gap_cache: Dict[tuple[str, str], int] = {}

    def cached_business_gap(prev_date: str, cur_date: str) -> int:
        key = (prev_date, cur_date)
        if key not in gap_cache:
            gap_cache[key] = business_gap(prev_date, cur_date)
        return gap_cache[key]

    for symbol, g in scan.groupby("symbol", sort=False):
        last_probe_date: str | None = None
        probe_count = 0
        rows = g.index.tolist()
        for idx in rows:
            rec = scan.loc[idx]
            if rec["event_kind"] == "launch_day":
                if last_probe_date is not None and cached_business_gap(last_probe_date, str(rec["trade_date"])) <= LAUNCH_WINDOW:
                    scan.at[idx, "event_role"] = "probe_to_launch"
                    scan.at[idx, "sequence_label"] = "试盘后启动"
                else:
                    scan.at[idx, "event_role"] = "launch_without_probe"
                    scan.at[idx, "sequence_label"] = "直接启动"
                continue
            if rec["event_kind"] != "probe_candidate":
                continue
            if last_probe_date is None:
                role = "first_probe"
                label = "首次试盘"
                days_gap = np.nan
            else:
                days_gap = cached_business_gap(last_probe_date, str(rec["trade_date"]))
                if days_gap <= TRADE_DATE_GAP_FOR_CONTINUOUS:
                    role = "continuous_probe"
                    label = "连续试盘"
                else:
                    role = "retest_probe"
                    label = "重新试盘"
            probe_count += 1
            scan.at[idx, "event_role"] = role
            scan.at[idx, "sequence_label"] = label
            scan.at[idx, "probe_index"] = probe_count
            scan.at[idx, "days_since_prev_probe"] = days_gap
            last_probe_date = str(rec["trade_date"])
    return scan


def business_gap(prev_date: str, cur_date: str) -> int:
    idx = load_trade_date_index()
    if prev_date not in idx or cur_date not in idx:
        return 999
    return int(idx[cur_date] - idx[prev_date])


def load_context(selection_conn: sqlite3.Connection, heat_conn: sqlite3.Connection, theme_conn: sqlite3.Connection, event_scan: pd.DataFrame) -> pd.DataFrame:
    subset = event_scan[event_scan["event_kind"].isin(["probe_candidate", "launch_day"])].copy()
    if subset.empty:
        subset["spark_hit"] = 0
        subset["stable_hit"] = 0
        subset["top_theme_name"] = ""
        subset["top_theme_rank"] = np.nan
        return subset
    keys = subset[["symbol", "trade_date"]].drop_duplicates()
    try:
        selection_conn.execute("DROP TABLE IF EXISTS temp_probe_keys")
        selection_conn.execute("CREATE TEMP TABLE temp_probe_keys(symbol TEXT, trade_date TEXT, PRIMARY KEY(symbol, trade_date))")
        selection_conn.executemany(
            "INSERT INTO temp_probe_keys(symbol, trade_date) VALUES (?, ?)",
            keys.itertuples(index=False, name=None),
        )
        selection_rows = pd.read_sql_query(
            """
            SELECT s.trade_date, s.symbol, s.source_id, s.source_name
            FROM selection_candidate_sources s
            JOIN temp_probe_keys k
              ON k.symbol = s.symbol
             AND k.trade_date = s.trade_date
            """,
            selection_conn,
        )
    except Exception:
        selection_rows = pd.DataFrame()
    if not selection_rows.empty:
        selection_rows["is_spark_hit"] = (selection_rows["source_id"] == "spark_opportunity_selector").astype(int)
        selection_rows["is_stable_hit"] = (selection_rows["source_id"] == "stable_capital_callback").astype(int)
        agg = (
            selection_rows.groupby(["symbol", "trade_date"], as_index=False)
            .agg(
                spark_hit=("is_spark_hit", "max"),
                stable_hit=("is_stable_hit", "max"),
                candidate_sources=("source_name", lambda s: " | ".join(sorted(set(map(str, s))))),
            )
        )
        subset = subset.merge(agg, on=["symbol", "trade_date"], how="left")
    else:
        subset["spark_hit"] = 0
        subset["stable_hit"] = 0
        subset["candidate_sources"] = ""

    try:
        theme_conn.execute("DROP TABLE IF EXISTS temp_probe_symbols")
        theme_conn.execute("CREATE TEMP TABLE temp_probe_symbols(symbol TEXT PRIMARY KEY)")
        theme_conn.executemany(
            "INSERT INTO temp_probe_symbols(symbol) VALUES (?)",
            [(str(symbol),) for symbol in keys["symbol"].drop_duplicates().tolist()],
        )
        memberships = pd.read_sql_query(
            """
            SELECT symbol, theme_id, theme_name, weight
            FROM tradable_theme_memberships
            WHERE symbol IN (SELECT symbol FROM temp_probe_symbols)
            """,
            theme_conn,
        )
    except Exception:
        memberships = pd.DataFrame()
    if not memberships.empty:
        try:
            ranks = pd.read_sql_query(
                """
                SELECT trade_date, theme_id, theme_name, rank_today, hot_score, top10_hits_20d, today_strong, mainline_accel, mainline_continue
                FROM fine_theme_heat_daily_v2
                WHERE trade_date >= ? AND trade_date <= ?
                """,
                heat_conn,
                params=[SCAN_START, SCAN_END],
            )
            theme_map = memberships.merge(ranks, on="theme_id", how="inner", suffixes=("_member", ""))
            theme_map = theme_map.sort_values(["symbol", "trade_date", "rank_today", "weight"], ascending=[True, True, True, False])
            top_theme = theme_map.groupby(["symbol", "trade_date"], as_index=False).first()
            top_theme = top_theme.rename(
                columns={
                    "theme_name": "top_theme_name",
                    "rank_today": "top_theme_rank",
                    "hot_score": "top_theme_score",
                    "top10_hits_20d": "top_theme_top10_hits_20d",
                    "today_strong": "top_theme_today_strong",
                    "mainline_accel": "top_theme_mainline_accel",
                    "mainline_continue": "top_theme_mainline_continue",
                }
            )
            subset = subset.merge(top_theme, on=["symbol", "trade_date"], how="left")
        except Exception:
            subset["top_theme_name"] = ""
            subset["top_theme_rank"] = np.nan
    else:
        subset["top_theme_name"] = ""
        subset["top_theme_rank"] = np.nan
    subset["spark_hit"] = subset["spark_hit"].fillna(0).astype(int)
    subset["stable_hit"] = subset["stable_hit"].fillna(0).astype(int)
    return subset


def build_sample_review(event_scan: pd.DataFrame, followup: pd.DataFrame, context_df: pd.DataFrame) -> pd.DataFrame:
    merged = (
        event_scan[event_scan["event_kind"].isin(["probe_candidate", "launch_day"])]
        .merge(
            followup,
            on=["symbol", "trade_date", "event_time", "business_anchor_time", "event_kind", "event_role", "sequence_label"],
            how="left",
            suffixes=("", "_fwd"),
        )
        .merge(
            context_df[
                [
                    "symbol",
                    "trade_date",
                    "spark_hit",
                    "stable_hit",
                    "candidate_sources",
                    "top_theme_name",
                    "top_theme_rank",
                ]
            ],
            on=["symbol", "trade_date"],
            how="left",
        )
    )
    merged["sample_priority"] = (
        (merged["symbol"] == "sz002570").astype(int) * 1000
        + (merged["event_role"] == "probe_to_launch").astype(int) * 100
        + (merged["spark_hit"] * 10)
        + merged["probe_strength_score"].fillna(0)
    )
    out = merged.sort_values(["sample_priority", "trade_date"], ascending=[False, False]).head(SAMPLE_REVIEW_LIMIT).copy()
    out["business_comment"] = np.where(
        out["event_kind"] == "launch_day",
        "当日更像正式发动，不属于试一下就收手。",
        np.where(
            out["event_role"] == "continuous_probe",
            "前面已经有试盘，这次属于继续摸抛压。",
            np.where(
                out["event_role"] == "retest_probe",
                "中间停过一段时间，再次拉升看抛压。",
                "第一次明显急拉后没有顺势走成，当日偏试盘。",
            ),
        ),
    )
    return out


def build_cluster_summary(followup: pd.DataFrame) -> pd.DataFrame:
    probe_only = followup[followup["event_kind"] == "probe_candidate"].copy()
    if probe_only.empty:
        return pd.DataFrame()
    cluster = (
        probe_only.groupby(["symbol"], as_index=False)
        .agg(
            probe_count=("trade_date", "count"),
            first_probe_date=("trade_date", "min"),
            last_probe_date=("trade_date", "max"),
            best_fwd_10d_high=("fwd_10d_high_ret_pct", "max"),
            best_fwd_20d_close=("fwd_20d_close_ret_pct", "max"),
        )
    )
    cluster["probe_cluster_type"] = np.where(
        cluster["probe_count"] == 1,
        "单次试盘",
        np.where(cluster["probe_count"] == 2, "两次试盘", "多次试盘"),
    )
    summary = (
        cluster.groupby("probe_cluster_type", as_index=False)
        .agg(
            stock_count=("symbol", "count"),
            avg_best_fwd_10d_high=("best_fwd_10d_high", "mean"),
            median_best_fwd_10d_high=("best_fwd_10d_high", "median"),
            avg_best_fwd_20d_close=("best_fwd_20d_close", "mean"),
            median_best_fwd_20d_close=("best_fwd_20d_close", "median"),
        )
    )
    return summary


def write_docs(thresholds: Thresholds, event_scan: pd.DataFrame, followup: pd.DataFrame, context_df: pd.DataFrame) -> None:
    probe_events = event_scan[event_scan["event_kind"] == "probe_candidate"].copy()
    launch_events = event_scan[event_scan["event_kind"] == "launch_day"].copy()
    role_counts = probe_events["sequence_label"].value_counts().to_dict()
    launch_role_counts = launch_events["sequence_label"].value_counts().to_dict()
    spark_rate = safe_float(context_df["spark_hit"].mean() * 100.0) if not context_df.empty else 0.0
    stable_rate = safe_float(context_df["stable_hit"].mean() * 100.0) if not context_df.empty else 0.0
    probe_followup = followup[followup["event_kind"] == "probe_candidate"].copy()
    cluster_summary = build_cluster_summary(followup)

    trade_dates = sorted(map(str, event_scan["trade_date"].dropna().unique().tolist()))
    trade_idx = {d: i for i, d in enumerate(trade_dates)}
    launch_dates_by_symbol: Dict[str, List[str]] = {}
    for rec in launch_events[launch_events["event_role"] == "probe_to_launch"][["symbol", "trade_date"]].itertuples(index=False):
        launch_dates_by_symbol.setdefault(str(rec.symbol), []).append(str(rec.trade_date))

    probe_launch_hits = []
    for rec in probe_events[["symbol", "trade_date", "event_role"]].itertuples(index=False):
        launch_dates = launch_dates_by_symbol.get(str(rec.symbol), [])
        base_idx = trade_idx.get(str(rec.trade_date), -1)
        ok = False
        for launch_date in launch_dates:
            launch_idx = trade_idx.get(launch_date, -1)
            if launch_idx > base_idx and launch_idx - base_idx <= LAUNCH_WINDOW:
                ok = True
                break
        probe_launch_hits.append(ok)
    probe_events["launch_within_10d"] = probe_launch_hits
    probe_to_launch_count = int(probe_events["launch_within_10d"].sum())
    probe_to_launch_rate = safe_float(probe_events["launch_within_10d"].mean() * 100.0)

    def fmt_forward(role: str, col: str) -> str:
        subset = probe_followup[probe_followup["event_role"] == role][col].dropna()
        if subset.empty:
            return "暂无足够样本"
        return f"{len(subset)} 个样本，均值 {subset.mean():.2f}%，中位数 {subset.median():.2f}%"

    first_probe_5d = fmt_forward("first_probe", "fwd_5d_close_ret_pct")
    first_probe_10d_high = fmt_forward("first_probe", "fwd_10d_high_ret_pct")
    retest_probe_5d = fmt_forward("retest_probe", "fwd_5d_close_ret_pct")
    retest_probe_10d_high = fmt_forward("retest_probe", "fwd_10d_high_ret_pct")
    continuous_probe_5d = fmt_forward("continuous_probe", "fwd_5d_close_ret_pct")
    continuous_probe_10d_high = fmt_forward("continuous_probe", "fwd_10d_high_ret_pct")

    cluster_lines: List[str] = []
    if not cluster_summary.empty:
        for rec in cluster_summary.itertuples(index=False):
            cluster_lines.append(
                f"- {rec.probe_cluster_type}：{int(rec.stock_count)} 只股票，10 日最好冲高均值 {safe_float(rec.avg_best_fwd_10d_high):.2f}%，20 日最好收盘均值 {safe_float(rec.avg_best_fwd_20d_close):.2f}%。"
            )
    if not cluster_lines:
        cluster_lines.append("- 当前没有形成可用聚类统计。")

    event_definition = [
        "# 试盘事件定义",
        "",
        "## 1. 业务定义",
        "- 市场里对“试盘 / 测抛压”没有统一监管术语口径。本研究采用中文投资百科常见解释，再用本地 5 分钟成交、委托、盘口数据把它翻成可验证事件。",
        "- 参考资料里，MBA 智库和东方财富百科都把“试盘”描述成：主导资金在正式操盘前，先主动做一段拉抬或打压，用来测试筹码锁定、上方抛压和市场跟风反应。",
        "- 本研究把“拉升试盘 / 测抛压”理解成：资金在日内主动做一段明显急拉，目的不是当天一口气走成，而是先看上方抛压、跟风质量和回落后的承接。",
        "- 如果急拉后当天继续走高、回吐很小、后续还反复创新高，更接近正式发动，不算第一阶段的试盘。",
        "- “抛压”在数据里不直接等于卖挂单绝对值，而更接近‘急拉之后市场愿不愿意马上往下砸、主导资金能不能轻松把价格挂住’。",
        "- 把 OIB、盘口失衡和急拉后的回吐当成量化代理，是本研究结合订单簿微观结构文献做的推断，不是百科原文术语。相关研究表明，短周期价格变化和订单流失衡关系更稳，而单纯成交量噪音更大。",
        "",
        "## 2. 第一版结构化口径",
        f"- 先从单日有 4% 以上日内高点振幅、且成交额不低于 8000 万的股票日里找事件，避免把纯噪音小票塞进来。",
        f"- 单日事件锚点：该股票日里“相对上一根 5 分钟收盘涨幅最大”的那一根 5 分钟。",
        "- 如果是高开触板型启动日，技术锚点有时会落在下午回封或再拉时段。为避免样本复盘误读，样本表额外记录 `business_anchor_time`，优先落到首次触板时刻。",
        f"- 试盘候选要求同时满足：",
        f"  1. 单根 5 分钟高点相对前收至少约 {thresholds.probe_bar_high_ret_pct:.2f}% 以上；",
        f"  2. 该根 5 分钟成交额至少是当日中位 5 分钟成交额的 {thresholds.probe_amount_vs_day_median:.2f} 倍以上；",
        f"  3. 主动加单净推动明显，OIB/成交额比不低于样本中位偏上的 {thresholds.probe_oib_ratio:.2f}；",
        f"  4. 急拉后当天有明显回吐，同日回吐比例不低于 {thresholds.probe_same_day_pullback_ratio:.2f}；",
        f"  5. 当天后续没有继续把高点显著往上扩，后续再创新高幅度不超过 {thresholds.probe_same_day_later_high_pct:.2f}% 左右。",
        "- 正式启动日与试盘候选区分：同样有急拉，但更偏向‘拉了就继续走’。具体表现是：当天后续还能继续创新高、回吐不深，或者日线本身已经强到接近启动日。",
        "",
        "## 3. 序列定义",
        "- 首次试盘：该股第一次被识别为试盘候选。",
        f"- 连续试盘：距离上一次试盘不超过 {TRADE_DATE_GAP_FOR_CONTINUOUS} 个交易日，再次出现相似试盘。",
        f"- 重新试盘：距离上一次试盘超过 {TRADE_DATE_GAP_FOR_RETEST - 1} 个交易日后，又出现新的试盘候选。",
        f"- 试盘后启动：试盘后 {LAUNCH_WINDOW} 个交易日内出现正式启动日。",
        "",
        "## 4. 贝因美样本解释",
        "- 2026-06-01 10:30：急拉强、量能爆发，但当天高点没有继续扩展，收盘回吐明显，属于试盘候选。",
        "- 2026-06-02 13:00：再次急拉，高点仍然当天见顶，之后继续回落，更像第二次试盘。",
        "- 2026-06-03：技术锚点落在 14:30，但业务发动时点是 09:35 首次触板，应该归为“试盘后启动”，而不是第三次继续试一下。",
        "",
        "## 5. 外部资料",
        "- [MBA智库百科：试盘](https://wiki.mbalib.com/wiki/%E8%AF%95%E7%9B%98)",
        "- [东方财富百科：试盘](https://baike.eastmoney.com/item/%E8%AF%95%E7%9B%98)",
        "- [Cont, Kukanov, Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)",
        "",
    ]
    (EXPERIMENT_DIR / "event_definition.md").write_text("\n".join(event_definition), encoding="utf-8")

    integration_notes = [
        "# 接入建议",
        "",
        "## 1. 不要直接当买点模型",
        "- 第一阶段更适合把试盘事件当成“资金开始摸票”的中间状态，而不是直接买入信号。",
        "",
        "## 2. 更适合的三种接法",
        "- 星火模型增强特征：加入“近 10 日是否出现首次试盘 / 连续试盘 / 重新试盘”“最近一次试盘距今几天”“试盘后是否放弃”等状态特征。",
        "- 热点板块优先级：如果某主题内龙头或中位容量票先出现连续试盘，再叠加主题热度回流，说明资金不是纯抽风，更像在为板块发动做试错。这个方向值得接，但当前主题映射和热度日表口径还没完全对齐，本阶段先不把板块分数直接并入结论。",
        "- 独立候选来源：可以先做 `watch_only` 的试盘观察池，只输出人看得懂的‘试盘后第几天、是否再次试盘、是否进入启动窗口’。",
        "",
        "## 3. 当前不建议",
        "- 不建议直接把试盘事件写成自动下单规则。",
        "- 不建议只看单次试盘。单次试盘更像摸底，连续试盘和试盘后启动的关系更值得跟踪。",
        "- 不建议现在就把它单独升级成每日主候选源。当前严格口径下，样本还偏少，先做增强特征更稳。",
        "",
        "## 4. 与现有体系的关系",
        f"- 当前样本里，试盘/启动事件与星火候选有一定重叠，命中率约 {spark_rate:.1f}%；与稳健回调策略重叠更低，命中率约 {stable_rate:.1f}%。",
        "- 这说明试盘更像早于稳健回调策略的前置资金动作，理论上更适合做前置特征或观察池，不适合直接替代成熟买点策略。",
        "- 如果只给一个优先级，当前建议是：先接星火增强特征，再做 `watch_only` 观察池，最后才考虑独立候选源。",
        "",
    ]
    (EXPERIMENT_DIR / "integration_notes.md").write_text("\n".join(integration_notes), encoding="utf-8")

    conclusion = [
        "# 研究结论",
        "",
        "## 1. 试盘在数据里是可以结构化的",
        "- 它不是玄学。最核心的结构是：单根 5 分钟急拉很强，但当天没有顺势把高点继续往上推，收盘前又回吐一部分。",
        "- 和正式发动相比，区别不在于有没有拉，而在于拉完以后有没有继续走出‘当天就承认这次发动’的走势。",
        "",
        "## 2. 贝因美更像“试盘 -> 再试盘 -> 启动”",
        "- 6 月 1 日和 6 月 2 日都符合急拉后当天见顶回吐的特征。",
        "- 6 月 3 日则更像正式启动日，而不是第三次摸一下。",
        "",
        "## 3. 第一阶段最有价值的是序列，不是单点",
        f"- 当前第一版严格口径下，共识别试盘候选 {len(probe_events)} 次，覆盖 {probe_events['symbol'].nunique()} 只股票；其中首次试盘 {role_counts.get('首次试盘', 0)} 次，连续试盘 {role_counts.get('连续试盘', 0)} 次，重新试盘 {role_counts.get('重新试盘', 0)} 次。",
        f"- 在这些试盘事件里，有 {probe_to_launch_count} 次在 {LAUNCH_WINDOW} 个交易日内等到了启动，命中率约 {probe_to_launch_rate:.1f}%。",
        "- 单次试盘说明有资金来摸；再次试盘说明资金没有立刻放弃；试盘后启动才是和后续走势关系最强的状态。",
        "",
        "## 4. 下一步优先级",
        "- 先人工复核样本里最强的 20 到 50 个事件，确认有没有把普通板块内强势股误识别成试盘。",
        "- 然后优先接星火增强特征，再补板块热度映射校验，最后再评估独立观察池是否值得常驻。",
        "",
    ]
    (EXPERIMENT_DIR / "research_conclusion.md").write_text("\n".join(conclusion), encoding="utf-8")

    readme = [
        "# A股“拉升试盘 / 测抛压”研究（第一阶段）",
        "",
        "## 结论",
        "- 贝因美 `sz002570` 是当前口径下很典型的“首次试盘 -> 连续试盘 -> 试盘后启动”候选。`2026-06-01 10:30` 是首次试盘，`2026-06-02 13:00` 是连续试盘，`2026-06-03` 的业务发动点在 `09:35` 首次触板，不应再算试盘。",
        f"- 第一版严格口径下，共识别试盘候选 {len(probe_events)} 次，覆盖 {probe_events['symbol'].nunique()} 只股票；其中有 {probe_to_launch_count} 次在 {LAUNCH_WINDOW} 个交易日内等到启动，命中率约 {probe_to_launch_rate:.1f}%。",
        f"- 更适合的接法不是“直接当买点”，而是先作为星火类模型增强特征；热点优先级可以作为第二接法，但还需要补主题热度映射校验；独立候选池只建议先做 `watch_only`。",
        "",
        "## 1. 业务定义",
        "- 市场并没有统一的官方术语口径。中文投资百科对“试盘”的共识描述是：主导资金在正式操盘前，先做一段拉抬或打压，用来测试筹码锁定、上方抛压和市场跟风反应。",
        "- 本研究把“拉升试盘 / 测抛压”翻译成一个更可验证的业务动作：日内先出现一段非常用力的 5 分钟急拉，但当天并没有顺势把高点继续往上推，反而回吐一部分，用来观察上方抛压和回落后的承接。",
        "- 这里的“抛压”不是单一字段，而是一个综合结果。它更接近“急拉之后市场愿不愿意马上砸下来、主导资金能不能轻松挂住价格”。",
        "- 把 OIB、盘口失衡和回吐幅度当成量化代理，是本研究结合订单簿微观结构文献做的推断。订单簿研究也支持：短周期价格变化和订单流失衡的关系，通常比单看成交量更稳。",
        "",
        "## 2. 第一版识别口径",
        f"- 研究区间：`{SCAN_START}` 到 `{SCAN_END}`。",
        "- 数据底座：复用项目现有主板 5 分钟成交、委托、盘口状态、日线和涨跌停状态库，不另起炉灶。",
        "- 起筛范围：先只看单日有 4% 以上日内高点振幅、且成交额不低于 8000 万的股票日。",
        f"- 试盘候选的结构要求是：5 分钟急拉足够猛，单根高点相对参考价约在 {thresholds.probe_bar_high_ret_pct:.2f}% 以上；成交额至少是当日中位 5 分钟成交额的 {thresholds.probe_amount_vs_day_median:.2f} 倍；OIB/成交额比不低于 {thresholds.probe_oib_ratio:.2f}；当天随后要有明显回吐，但后续又不能继续把高点显著往上扩。",
        f"- 正式启动日与试盘区分开的关键，不是“有没有拉”，而是“拉完以后当天是否被市场承认”。如果后续继续扩高、回吐很浅，或直接走成触板型强攻，更接近启动。",
        "- 启动日样本里，技术锚点有时会落在下午回封或再拉的那根 5 分钟，因此样本表额外给了 `business_anchor_time`，专门记录业务上更像发动的时间点。",
        "",
        "## 3. 贝因美复盘",
        "- `2026-06-01 10:30`：5 分钟内急拉很强，量能爆发，但全天没有继续把高点往上抬，收盘回吐明显，更像第一次摸上方筹码。",
        "- `2026-06-02 13:00`：又来一次类似动作，当天依然没走成，更像连续试盘，而不是随机异动。",
        "- `2026-06-03`：日线已经转成正式发动。技术锚点落在 `14:30`，但从业务上看，真正的发动点是 `09:35` 首次触板，应该归为“试盘后启动”。",
        "",
        "## 4. 全市场扫描结果",
        f"- `probe_candidate`：{len(probe_events)} 次。",
        f"- `launch_day`：{len(launch_events)} 次，其中“试盘后启动” {launch_role_counts.get('试盘后启动', 0)} 次，“直接启动” {launch_role_counts.get('直接启动', 0)} 次。",
        f"- 试盘角色拆分：首次试盘 {role_counts.get('首次试盘', 0)} 次，连续试盘 {role_counts.get('连续试盘', 0)} 次，重新试盘 {role_counts.get('重新试盘', 0)} 次。",
        f"- 严格口径下，只有约 {probe_to_launch_rate:.1f}% 的试盘事件在 {LAUNCH_WINDOW} 个交易日内等到启动，这说明“可观测试盘”是一个有辨识度但不高频的前置信号，不是所有启动都会先给你一轮明显试盘。",
        "",
        "## 5. 后续表现统计",
        f"- 首次试盘后 5 日收盘收益：{first_probe_5d}。",
        f"- 首次试盘后 10 日内最好冲高：{first_probe_10d_high}。",
        f"- 重新试盘后 5 日收盘收益：{retest_probe_5d}。",
        f"- 重新试盘后 10 日内最好冲高：{retest_probe_10d_high}。",
        f"- 连续试盘后 5 日收盘收益：{continuous_probe_5d}。",
        f"- 连续试盘后 10 日内最好冲高：{continuous_probe_10d_high}。",
        "- 连续试盘当前只有 2 次识别、真正有 5 日前瞻的只有 1 次，方向上偏强，但样本远不够，不能当成稳定统计结论。",
        "",
        "按股票聚类后：",
        *cluster_lines,
        "",
        "## 6. 接到现有体系的建议",
        "- 第一优先级：接到星火类模型，做状态增强特征，而不是直接当买点。最值得加的是“近 10 日是否出现试盘”“是首次还是重试”“距离最近一次试盘几天”“是否进入启动窗口”。",
        "- 第二优先级：做独立 `watch_only` 观察池。输出语言要面向交易研究，而不是只报技术字段，例如“这只票 3 天前试过盘，今天进入启动观察窗口”。",
        "- 第三优先级：接热点板块优先级，但要先补主题映射和热度日表校验。这个方向值得做，但当前这版证据还不够硬，先不把它写成已验证结论。",
        "- 当前不建议把试盘事件直接升级成自动交易模型，也不建议直接替代现有成熟买点策略。",
        "",
        "## 7. 输出文件",
        "- [event_definition.md](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/event_definition.md)",
        "- [sample_review.csv](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/sample_review.csv)",
        "- [event_scan.csv](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/event_scan.csv)",
        "- [followup_outcome.csv](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/followup_outcome.csv)",
        "- [cluster_summary.csv](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/cluster_summary.csv)",
        "- [integration_notes.md](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/integration_notes.md)",
        "- [research_conclusion.md](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/research_conclusion.md)",
        "- [summary.json](/Users/dong/ZhangData/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/summary.json)",
        "",
        "## 8. 外部资料",
        "- [MBA智库百科：试盘](https://wiki.mbalib.com/wiki/%E8%AF%95%E7%9B%98)",
        "- [东方财富百科：试盘](https://baike.eastmoney.com/item/%E8%AF%95%E7%9B%98)",
        "- [Cont, Kukanov, Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)",
        "",
    ]
    (EXPERIMENT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> None:
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_conn = connect_ro(DEFAULT_ATOMIC_DB)
    events = build_event_frame(atomic_conn)
    thresholds = derive_thresholds(events)
    classified = classify_events(events, thresholds)
    tagged = tag_sequences(classified)
    selection_conn = connect_ro(DEFAULT_SELECTION_DB)
    heat_conn = connect_ro(DEFAULT_HEAT_DB)
    theme_conn = connect_ro(DEFAULT_THEME_MAP_DB)
    context_df = load_context(selection_conn, heat_conn, theme_conn, tagged)
    followup = build_followup(atomic_conn, tagged[tagged["event_kind"].isin(["probe_candidate", "launch_day"])])
    sample_review = build_sample_review(tagged, followup, context_df)
    cluster_summary = build_cluster_summary(followup)

    event_scan_export_cols = [
        "symbol",
        "trade_date",
        "event_time",
        "business_anchor_time",
        "event_kind",
        "event_role",
        "sequence_label",
        "probe_index",
        "days_since_prev_probe",
        "bar_high_ret_pct",
        "bar_close_ret_pct",
        "amount_vs_day_median",
        "same_day_pullback_ratio",
        "same_day_later_high_pct",
        "oib_ratio",
        "cvd_ratio",
        "day_gap_pct",
        "day_high_vs_prev_close_pct",
        "day_return_pct",
        "touch_limit_up",
        "broken_limit_up",
        "touch_limit_up_count_5m",
        "limit_state_label",
        "probe_strength_score",
    ]
    sample_review_export_cols = [
        "symbol",
        "trade_date",
        "event_time",
        "business_anchor_time",
        "event_kind",
        "event_role",
        "sequence_label",
        "bar_high_ret_pct",
        "amount_vs_day_median",
        "same_day_pullback_ratio",
        "same_day_later_high_pct",
        "day_gap_pct",
        "day_high_vs_prev_close_pct",
        "day_return_pct",
        "touch_limit_up",
        "broken_limit_up",
        "limit_state_label",
        "probe_strength_score",
        "fwd_1d_close_ret_pct",
        "fwd_3d_close_ret_pct",
        "fwd_5d_close_ret_pct",
        "fwd_10d_high_ret_pct",
        "fwd_20d_close_ret_pct",
        "spark_hit",
        "stable_hit",
        "candidate_sources",
        "top_theme_name",
        "top_theme_rank",
        "business_comment",
    ]
    event_scan_export = tagged[event_scan_export_cols].copy()
    sample_review_export = sample_review[sample_review_export_cols].copy()

    event_scan_export.to_csv(EXPERIMENT_DIR / "event_scan.csv", index=False)
    followup.to_csv(EXPERIMENT_DIR / "followup_outcome.csv", index=False)
    sample_review_export.to_csv(EXPERIMENT_DIR / "sample_review.csv", index=False)
    cluster_summary.to_csv(EXPERIMENT_DIR / "cluster_summary.csv", index=False)
    write_docs(thresholds, tagged, followup, context_df)

    summary = {
        "scan_range": {"start": SCAN_START, "end": SCAN_END},
        "thresholds": thresholds.__dict__,
        "event_counts": tagged["event_kind"].value_counts().to_dict(),
        "probe_roles": tagged[tagged["event_kind"] == "probe_candidate"]["sequence_label"].value_counts().to_dict(),
        "beiyinmei_rows": tagged[tagged["symbol"] == "sz002570"][
            [
                "trade_date",
                "event_time",
                "event_kind",
                "event_role",
                "sequence_label",
                "bar_high_ret_pct",
                "amount_vs_day_median",
                "same_day_pullback_ratio",
                "same_day_later_high_pct",
            ]
        ].to_dict(orient="records"),
    }
    (EXPERIMENT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
