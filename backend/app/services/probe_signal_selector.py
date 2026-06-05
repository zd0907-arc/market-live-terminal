from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import RESEARCH_CURRENT_ROOT
from backend.app.db.selection_db import get_selection_connection

ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = Path(RESEARCH_CURRENT_ROOT)
ATOMIC_DB = RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
FEATURE_DB = RESEARCH_ROOT / "selection" / "model_feature_store.db"
ARTIFACT_PATH = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"

WATCH_SOURCE_ID = "probe_day0_watch"
WATCH_SOURCE_NAME = "试盘观察池"
WATCH_SOURCE_VERSION = "probe_watch_v1"

CONFIRM_SOURCE_ID = "probe_d3_confirmed"
CONFIRM_SOURCE_NAME = "试盘D3确认池"
CONFIRM_SOURCE_VERSION = "probe_confirm_v1"

WATCH_SOURCE_LIMIT = 12
CONFIRM_SOURCE_LIMIT = 8

TRAINED_THRESHOLDS = {
    "probe_bar_high_ret_pct": 4.7169811320754595,
    "probe_bar_close_ret_pct": 2.7322404371584508,
    "probe_amount_vs_day_median": 13.030978210890266,
    "probe_same_day_pullback_ratio": 0.3571428571428557,
    "probe_same_day_later_high_pct": 0.0,
    "probe_oib_ratio": 0.25499109284286353,
    "launch_same_day_later_high_pct": 2.564760194921778,
    "launch_close_pullback_ratio_max": -0.1896551724137921,
    "launch_day_return_pct": 5.700871898054993,
}

PROBE_MIN_HISTORY_SAMPLES = 8
PROBE_MAX_HISTORY_SAMPLES = 60
PROBE_SIMILAR_CASE_LIMIT = 3
PROBE_FUTURE_WINDOW_DAYS = 10


@dataclass(frozen=True)
class ProbeThresholds:
    probe_bar_high_ret_pct: float
    probe_bar_close_ret_pct: float
    probe_amount_vs_day_median: float
    probe_same_day_pullback_ratio: float
    probe_same_day_later_high_pct: float
    probe_oib_ratio: float
    launch_same_day_later_high_pct: float
    launch_close_pullback_ratio_max: float
    launch_day_return_pct: float


THRESHOLDS = ProbeThresholds(**TRAINED_THRESHOLDS)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path.expanduser().resolve()), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=120000")
    return conn


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    return text


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    return str(value)


def _symbol_name_map(symbols: Sequence[str], trade_date: str) -> Dict[str, str]:
    if not symbols:
        return {}
    conn = _connect(FEATURE_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_name_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_name_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_name_symbols(symbol) VALUES (?)", [(symbol,) for symbol in symbols])
        rows = conn.execute(
            """
            SELECT symbol, name
            FROM model_feature_daily_v1
            WHERE trade_date = ?
              AND symbol IN (SELECT symbol FROM temp_probe_name_symbols)
            """,
            (trade_date,),
        ).fetchall()
        return {str(row["symbol"]).lower(): _clean_text(row["name"], str(row["symbol"]).lower()) for row in rows}
    finally:
        conn.close()


def _next_trade_date(trade_date: str) -> Optional[str]:
    conn = _connect(ATOMIC_DB)
    try:
        row = conn.execute(
            """
            SELECT MIN(trade_date) AS next_date
            FROM atomic_trade_daily
            WHERE trade_date > ?
            """,
            (str(trade_date),),
        ).fetchone()
        return str(row["next_date"]) if row and row["next_date"] else None
    finally:
        conn.close()


def _prev_trade_date(trade_date: str) -> Optional[str]:
    conn = _connect(ATOMIC_DB)
    try:
        row = conn.execute(
            """
            SELECT MAX(trade_date) AS prev_date
            FROM atomic_trade_daily
            WHERE trade_date < ?
            """,
            (str(trade_date),),
        ).fetchone()
        return str(row["prev_date"]) if row and row["prev_date"] else None
    finally:
        conn.close()


def _feature_trade_date_exists(trade_date: str) -> bool:
    conn = _connect(FEATURE_DB)
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM model_feature_daily_v1
            WHERE trade_date = ?
            LIMIT 1
            """,
            (trade_date,),
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def _history_window_start(trade_date: str, calendar_days: int = 120) -> str:
    from datetime import datetime, timedelta

    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    return (dt - timedelta(days=calendar_days)).strftime("%Y-%m-%d")


def source_registry_records() -> List[Dict[str, Any]]:
    return [
        {
            "source_id": WATCH_SOURCE_ID,
            "source_name": WATCH_SOURCE_NAME,
            "source_type": "rule_strategy",
            "source_version": WATCH_SOURCE_VERSION,
            "artifact_version": WATCH_SOURCE_VERSION,
            "horizon": "watch",
            "status": "active",
            "owner_note": "试盘当天盘后观察池，只使用当日可见数据，不包含未来确认。",
            "description": "盘后识别当天疑似拉升试盘行为，供次日跟踪和后续确认。",
        },
        {
            "source_id": CONFIRM_SOURCE_ID,
            "source_name": CONFIRM_SOURCE_NAME,
            "source_type": "rule_strategy",
            "source_version": CONFIRM_SOURCE_VERSION,
            "artifact_version": CONFIRM_SOURCE_VERSION,
            "horizon": "swing",
            "status": "active",
            "owner_note": "试盘后第3日强确认池，允许使用 D3 确认，不回填到试盘当天。",
            "description": "试盘后第3日资金未撤、盘口承接仍在的强确认候选池。",
        },
    ]


def _load_feature_rows(trade_date: str, symbols: Sequence[str]) -> Dict[Tuple[str, str], sqlite3.Row]:
    if not symbols:
        return {}
    conn = _connect(FEATURE_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_feature_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_feature_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_feature_symbols(symbol) VALUES (?)", [(symbol,) for symbol in symbols])
        rows = conn.execute(
            """
            SELECT *
            FROM model_feature_daily_v1
            WHERE trade_date = ?
              AND symbol IN (SELECT symbol FROM temp_probe_feature_symbols)
            """,
            (trade_date,),
        ).fetchall()
        return {(str(row["symbol"]).lower(), str(row["trade_date"])): row for row in rows}
    finally:
        conn.close()


def _feature_series_for_symbols(symbols: Sequence[str], start_date: str, end_date: str) -> Dict[str, List[sqlite3.Row]]:
    if not symbols:
        return {}
    conn = _connect(FEATURE_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_feature_series_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_feature_series_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_feature_series_symbols(symbol) VALUES (?)", [(symbol,) for symbol in symbols])
        rows = conn.execute(
            """
            SELECT *
            FROM model_feature_daily_v1
            WHERE trade_date >= ?
              AND trade_date <= ?
              AND symbol IN (SELECT symbol FROM temp_probe_feature_series_symbols)
            ORDER BY symbol ASC, trade_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
        out: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            out.setdefault(str(row["symbol"]).lower(), []).append(row)
        return out
    finally:
        conn.close()


def _trade_rows_for_date(trade_date: str) -> List[sqlite3.Row]:
    conn = _connect(ATOMIC_DB)
    try:
        rows = conn.execute(
            """
            SELECT symbol, trade_date, open AS day_open, high AS day_high, low AS day_low, close AS day_close, total_amount AS day_amount
            FROM atomic_trade_daily
            WHERE trade_date = ?
              AND high / NULLIF(open, 0) >= 1.04
              AND total_amount >= 80000000
            ORDER BY symbol ASC
            """,
            (trade_date,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def _build_day_events(trade_date: str) -> List[Dict[str, Any]]:
    trade_rows = _trade_rows_for_date(trade_date)
    if not trade_rows:
        return []
    conn = _connect(ATOMIC_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_day_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_day_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany(
            "INSERT INTO temp_probe_day_symbols(symbol) VALUES (?)",
            [(str(row["symbol"]).lower(),) for row in trade_rows],
        )
        bars = conn.execute(
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
            LEFT JOIN atomic_order_5m o
              ON o.symbol = t.symbol
             AND o.bucket_start = t.bucket_start
            LEFT JOIN atomic_book_state_5m b
              ON b.symbol = t.symbol
             AND b.bucket_start = t.bucket_start
            WHERE t.trade_date = ?
              AND t.symbol IN (SELECT symbol FROM temp_probe_day_symbols)
            ORDER BY t.symbol ASC, t.bucket_start ASC
            """,
            (trade_date,),
        ).fetchall()
        limit_rows = conn.execute(
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
            WHERE trade_date = ?
              AND symbol IN (SELECT symbol FROM temp_probe_day_symbols)
            """,
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    by_symbol_bars: Dict[str, List[sqlite3.Row]] = {}
    for row in bars:
        by_symbol_bars.setdefault(str(row["symbol"]).lower(), []).append(row)
    limit_by_symbol = {str(row["symbol"]).lower(): row for row in limit_rows}
    prev_date = _prev_trade_date(trade_date)
    prev_close_lookup: Dict[str, float] = {}
    if prev_date:
        conn2 = _connect(ATOMIC_DB)
        try:
            conn2.execute("DROP TABLE IF EXISTS temp_probe_prev_symbols")
            conn2.execute("CREATE TEMP TABLE temp_probe_prev_symbols(symbol TEXT PRIMARY KEY)")
            conn2.executemany(
                "INSERT INTO temp_probe_prev_symbols(symbol) VALUES (?)",
                [(str(row["symbol"]).lower(),) for row in trade_rows],
            )
            rows = conn2.execute(
                """
                SELECT symbol, close
                FROM atomic_trade_daily
                WHERE trade_date = ?
                  AND symbol IN (SELECT symbol FROM temp_probe_prev_symbols)
                """,
                (prev_date,),
            ).fetchall()
            prev_close_lookup = {str(row["symbol"]).lower(): _safe_float(row["close"]) for row in rows}
        finally:
            conn2.close()

    result: List[Dict[str, Any]] = []
    for day_row in trade_rows:
        symbol = str(day_row["symbol"]).lower()
        symbol_bars = by_symbol_bars.get(symbol) or []
        if not symbol_bars:
            continue
        prev_bar_close: Optional[float] = None
        ranked: List[Dict[str, Any]] = []
        amounts = [_safe_float(row["total_amount"]) for row in symbol_bars if _safe_float(row["total_amount"]) > 0]
        amounts_sorted = sorted(amounts)
        median_amount = amounts_sorted[len(amounts_sorted) // 2] if amounts_sorted else 0.0
        day_high = _safe_float(day_row["day_high"])
        day_close = _safe_float(day_row["day_close"])
        day_open = _safe_float(day_row["day_open"])
        limit_prev_close = 0.0
        if symbol in limit_by_symbol:
            limit_prev_close = _safe_float(limit_by_symbol[symbol]["prev_close"])
        day_prev_close = prev_close_lookup.get(symbol) or limit_prev_close
        if not day_prev_close:
            day_prev_close = day_open
        for bar in symbol_bars:
            ref_price = prev_bar_close if prev_bar_close and prev_bar_close > 0 else _safe_float(bar["open"])
            prev_bar_close = _safe_float(bar["close"])
            if ref_price <= 0:
                continue
            high = _safe_float(bar["high"])
            close = _safe_float(bar["close"])
            total_amount = _safe_float(bar["total_amount"])
            if total_amount <= 0:
                continue
            oib_ratio = _safe_float(bar["oib_delta_amount"]) / total_amount if total_amount > 0 else 0.0
            cvd_ratio = _safe_float(bar["cvd_delta_amount"]) / total_amount if total_amount > 0 else 0.0
            add_buy_ratio = _safe_float(bar["add_buy_amount"]) / total_amount if total_amount > 0 else 0.0
            add_sell_ratio = _safe_float(bar["add_sell_amount"]) / total_amount if total_amount > 0 else 0.0
            cancel_buy_ratio = _safe_float(bar["cancel_buy_amount"]) / total_amount if total_amount > 0 else 0.0
            cancel_sell_ratio = _safe_float(bar["cancel_sell_amount"]) / total_amount if total_amount > 0 else 0.0
            bid_amt = _safe_float(bar["end_bid_resting_amount"])
            ask_amt = _safe_float(bar["end_ask_resting_amount"])
            ranked.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "bucket_start": _clean_text(bar["bucket_start"]),
                    "event_time": _clean_text(bar["bucket_start"])[11:16],
                    "open": _safe_float(bar["open"]),
                    "high": high,
                    "low": _safe_float(bar["low"]),
                    "close": close,
                    "total_amount": total_amount,
                    "bar_high_ret_pct": (high / ref_price - 1.0) * 100.0,
                    "bar_close_ret_pct": (close / ref_price - 1.0) * 100.0,
                    "amount_vs_day_median": (total_amount / median_amount) if median_amount > 0 else 0.0,
                    "oib_ratio": oib_ratio,
                    "cvd_ratio": cvd_ratio,
                    "add_buy_ratio": add_buy_ratio,
                    "add_sell_ratio": add_sell_ratio,
                    "cancel_buy_ratio": cancel_buy_ratio,
                    "cancel_sell_ratio": cancel_sell_ratio,
                    "buy_support_ratio": (bid_amt / ask_amt) if ask_amt > 0 else (2.0 if bid_amt > 0 else 0.0),
                    "sell_pressure_ratio": (ask_amt / bid_amt) if bid_amt > 0 else (2.0 if ask_amt > 0 else 0.0),
                    "support_pressure_spread": ((bid_amt - ask_amt) / (bid_amt + ask_amt)) if (bid_amt + ask_amt) > 0 else 0.0,
                    "close_book_imbalance_ratio": _safe_float(bar["book_imbalance_ratio"]),
                    "avg_book_imbalance_ratio": _safe_float(bar["book_imbalance_ratio"]),
                    "close_bid_ask_amount_ratio": (bid_amt / ask_amt) if ask_amt > 0 else (2.0 if bid_amt > 0 else 0.0),
                }
            )
        if not ranked:
            continue
        anchor = max(ranked, key=lambda item: item["bar_high_ret_pct"])
        same_day_pullback_ratio = 0.0
        if anchor["high"] > anchor["open"]:
            denom = anchor["high"] - anchor["open"]
            same_day_pullback_ratio = ((anchor["high"] - day_close) / denom) if denom > 0 else 0.0
        later_high = max((_safe_float(item["high"]) for item in ranked if item["bucket_start"] > anchor["bucket_start"]), default=anchor["high"])
        same_day_later_high_pct = (later_high / anchor["high"] - 1.0) * 100.0 if anchor["high"] > 0 else 0.0
        day_gap_pct = (day_open / day_prev_close - 1.0) * 100.0 if day_prev_close > 0 else 0.0
        day_return_pct = (day_close / day_open - 1.0) * 100.0 if day_open > 0 else 0.0
        day_high_vs_prev_close_pct = (day_high / day_prev_close - 1.0) * 100.0 if day_prev_close > 0 else 0.0
        limit_row = limit_by_symbol.get(symbol)
        limit_map = dict(limit_row) if limit_row is not None else {}
        anchor.update(
            {
                "same_day_pullback_ratio": same_day_pullback_ratio,
                "same_day_later_high_pct": same_day_later_high_pct,
                "day_gap_pct": day_gap_pct,
                "day_return_pct": day_return_pct,
                "day_high_vs_prev_close_pct": day_high_vs_prev_close_pct,
                "touch_limit_up": int(_safe_float(limit_map.get("touch_limit_up"))),
                "is_limit_up_close": int(_safe_float(limit_map.get("is_limit_up_close"))),
                "broken_limit_up": int(_safe_float(limit_map.get("broken_limit_up"))),
                "touch_limit_up_count_5m": int(_safe_float(limit_map.get("touch_limit_up_count_5m"))),
                "first_touch_limit_up_time": _clean_text(limit_map.get("first_touch_limit_up_time")),
                "limit_state_label": _clean_text(limit_map.get("limit_state_label")),
                "day_open": day_open,
                "day_close": day_close,
                "day_high": day_high,
                "day_prev_close": day_prev_close,
                "day_amount": _safe_float(day_row["day_amount"]),
            }
        )
        result.append(anchor)
    return result


def _is_probe_candidate(event: Dict[str, Any]) -> bool:
    return (
        _safe_float(event.get("bar_high_ret_pct")) >= THRESHOLDS.probe_bar_high_ret_pct
        and _safe_float(event.get("bar_close_ret_pct")) >= THRESHOLDS.probe_bar_close_ret_pct
        and _safe_float(event.get("amount_vs_day_median")) >= THRESHOLDS.probe_amount_vs_day_median
        and _safe_float(event.get("same_day_pullback_ratio")) >= THRESHOLDS.probe_same_day_pullback_ratio
        and _safe_float(event.get("same_day_later_high_pct")) <= THRESHOLDS.probe_same_day_later_high_pct + 1e-9
        and _safe_float(event.get("oib_ratio")) >= THRESHOLDS.probe_oib_ratio
        and _safe_float(event.get("day_return_pct")) < THRESHOLDS.launch_day_return_pct
    )


def _is_launch_day(event: Dict[str, Any]) -> bool:
    if (
        _safe_float(event.get("bar_high_ret_pct")) >= THRESHOLDS.probe_bar_high_ret_pct
        and _safe_float(event.get("amount_vs_day_median")) >= THRESHOLDS.probe_amount_vs_day_median
        and (
            _safe_float(event.get("same_day_later_high_pct")) > THRESHOLDS.launch_same_day_later_high_pct
            or _safe_float(event.get("same_day_pullback_ratio")) <= THRESHOLDS.launch_close_pullback_ratio_max
            or _safe_float(event.get("day_return_pct")) >= THRESHOLDS.launch_day_return_pct
        )
    ):
        return True
    return int(_safe_float(event.get("touch_limit_up"))) == 1 and _safe_float(event.get("day_high_vs_prev_close_pct")) >= 9.5


def _probe_strength_score(event: Dict[str, Any]) -> float:
    high_score = min(max((_safe_float(event.get("bar_high_ret_pct")) - THRESHOLDS.probe_bar_high_ret_pct) / 3.0, 0.0), 1.0)
    amt_score = min(max((_safe_float(event.get("amount_vs_day_median")) - THRESHOLDS.probe_amount_vs_day_median) / 12.0, 0.0), 1.0)
    oib_score = min(max((_safe_float(event.get("oib_ratio")) - THRESHOLDS.probe_oib_ratio) / 0.25, 0.0), 1.0)
    pullback_score = min(max((_safe_float(event.get("same_day_pullback_ratio")) - THRESHOLDS.probe_same_day_pullback_ratio) / 0.6, 0.0), 1.0)
    later_high_score = 1.0 if _safe_float(event.get("same_day_later_high_pct")) <= 0.0 else max(0.0, 1.0 - _safe_float(event.get("same_day_later_high_pct")) / 1.5)
    return round((high_score * 0.28 + amt_score * 0.22 + oib_score * 0.22 + pullback_score * 0.18 + later_high_score * 0.10) * 100.0, 4)


def _business_anchor_time(event: Dict[str, Any]) -> str:
    touch_time = _clean_text(event.get("first_touch_limit_up_time"))
    if touch_time:
        return touch_time[11:16] if len(touch_time) >= 16 else touch_time
    return _clean_text(event.get("event_time"))


def _trade_date_index(start_date: str, end_date: str) -> Dict[str, int]:
    conn = _connect(ATOMIC_DB)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_daily
            WHERE trade_date >= ?
              AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return {str(row["trade_date"]): idx for idx, row in enumerate(rows)}
    finally:
        conn.close()


def _business_gap(index_map: Dict[str, int], prev_date: Optional[str], cur_date: str) -> int:
    if not prev_date:
        return 999
    prev = index_map.get(prev_date)
    cur = index_map.get(cur_date)
    if prev is None or cur is None:
        return 999
    return int(cur - prev)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_feature_distance(value: float, center: float, scale: float) -> float:
    if scale <= 0:
        return abs(value - center)
    return abs(value - center) / scale


def _safe_pct_from_ratio(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number * 100.0


def _candidate_name(symbol: str, trade_date: str) -> str:
    mapping = _symbol_name_map([symbol], trade_date)
    return mapping.get(symbol.lower(), symbol.lower())


def _trade_date_calendar(start_date: str, end_date: str) -> List[str]:
    conn = _connect(ATOMIC_DB)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_daily
            WHERE trade_date >= ?
              AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return [str(row["trade_date"]) for row in rows]
    finally:
        conn.close()


def _trade_date_offset(anchor_date: str, offset: int) -> Optional[str]:
    start_date = _history_window_start(anchor_date, 260)
    dates = _trade_date_calendar(start_date, _history_window_start(anchor_date, -60))
    if not dates:
        return None
    try:
        idx = dates.index(anchor_date)
    except ValueError:
        return None
    target = idx + int(offset)
    if target < 0 or target >= len(dates):
        return None
    return dates[target]


def _history_cutoff_trade_date(trade_date: str) -> str:
    cutoff = _trade_date_offset(trade_date, -PROBE_FUTURE_WINDOW_DAYS)
    return cutoff or trade_date


def _history_bucket_label(value: float, *, edges: Sequence[float], labels: Sequence[str]) -> str:
    for idx, edge in enumerate(edges):
        if value < edge:
            return labels[idx]
    return labels[-1]


def _probe_strength_bucket(value: float) -> str:
    return _history_bucket_label(value, edges=(62.0, 75.0, 88.0), labels=("偏弱", "中等", "偏强", "很强"))


def _hot_rank_bucket(value: Any) -> str:
    rank = _safe_float(value, default=999.0)
    return _history_bucket_label(rank, edges=(10.5, 30.5, 80.5), labels=("前排", "中前排", "中位", "靠后"))


def _position_bucket(value: Any) -> str:
    pos = _safe_float(value, default=1.0)
    return _history_bucket_label(pos, edges=(0.35, 0.62, 0.82), labels=("低位", "中低位", "中高位", "高位"))


def _history_group_summary(sequence_label: str, strength_bucket: str, position_bucket: str, source_id: str) -> str:
    source_text = "D3确认" if source_id == CONFIRM_SOURCE_ID else "试盘观察"
    return f"{source_text} / {sequence_label} / {strength_bucket} / {position_bucket}"


def _load_probe_source_history(
    source_id: str,
    start_date: str,
    end_date: str,
    *,
    exclude_trade_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = get_selection_connection()
    try:
        params: List[Any] = [source_id, start_date, end_date]
        extra_filter = ""
        if exclude_trade_date:
            extra_filter = "AND trade_date != ?"
            params.append(exclude_trade_date)
        rows = conn.execute(
            f"""
            SELECT trade_date, symbol, name, source_id, explain_factors_json, raw_payload_json
            FROM selection_candidate_sources
            WHERE source_id = ?
              AND trade_date >= ?
              AND trade_date <= ?
              {extra_filter}
            ORDER BY trade_date ASC, symbol ASC
            """,
            params,
        ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            explain = json.loads(str(row["explain_factors_json"] or "{}"))
            raw = json.loads(str(row["raw_payload_json"] or "{}"))
            result.append(
                {
                    "trade_date": str(row["trade_date"]),
                    "symbol": str(row["symbol"]).lower(),
                    "name": _clean_text(row["name"], str(row["symbol"]).lower()),
                    "source_id": str(row["source_id"]),
                    "explain_factors": explain if isinstance(explain, dict) else {},
                    "raw_payload": raw if isinstance(raw, dict) else {},
                }
            )
        return result
    finally:
        conn.close()


def _load_daily_followthrough(symbol: str, trade_date: str, days: int = PROBE_FUTURE_WINDOW_DAYS) -> Optional[Dict[str, Any]]:
    end_date = _trade_date_offset(trade_date, days)
    if not end_date:
        return None
    conn = _connect(ATOMIC_DB)
    try:
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close
            FROM atomic_trade_daily
            WHERE symbol = ?
              AND trade_date >= ?
              AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (symbol.lower(), trade_date, end_date),
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < days + 1:
        return None
    anchor_close = _safe_float(rows[0]["close"])
    if anchor_close <= 0:
        return None
    forward_rows = list(rows[1 : days + 1])
    if len(forward_rows) < days:
        return None

    closes = [_safe_float(row["close"]) for row in forward_rows]
    highs = [_safe_float(row["high"]) for row in forward_rows]
    lows = [_safe_float(row["low"]) for row in forward_rows]
    close_ret = [((value / anchor_close) - 1.0) * 100.0 if anchor_close > 0 else None for value in closes]
    high_ret = [((value / anchor_close) - 1.0) * 100.0 if anchor_close > 0 else None for value in highs]
    low_ret = [((value / anchor_close) - 1.0) * 100.0 if anchor_close > 0 else None for value in lows]

    def _at(values: Sequence[Optional[float]], index_1based: int) -> Optional[float]:
        idx = index_1based - 1
        if idx < 0 or idx >= len(values):
            return None
        return values[idx]

    def _hit_day(values: Sequence[Optional[float]], threshold: float, direction: str) -> Optional[int]:
        for idx, value in enumerate(values, start=1):
            if value is None:
                continue
            if direction == "up" and value >= threshold:
                return idx
            if direction == "down" and value <= threshold:
                return idx
        return None

    return {
        "close_1d_pct": _at(close_ret, 1),
        "close_3d_pct": _at(close_ret, 3),
        "close_5d_pct": _at(close_ret, 5),
        "close_10d_pct": _at(close_ret, 10),
        "avg_return_5d_pct": _at(close_ret, 5),
        "avg_return_10d_pct": _at(close_ret, 10),
        "max_high_5d_pct": max((value for value in high_ret[:5] if value is not None), default=None),
        "max_high_10d_pct": max((value for value in high_ret[:10] if value is not None), default=None),
        "min_low_5d_pct": min((value for value in low_ret[:5] if value is not None), default=None),
        "min_low_10d_pct": min((value for value in low_ret[:10] if value is not None), default=None),
        "hit_up5_day": _hit_day(high_ret[:10], 5.0, "up"),
        "hit_up8_day": _hit_day(high_ret[:10], 8.0, "up"),
        "hit_down3_day": _hit_day(low_ret[:5], -3.0, "down"),
        "hit_down5_day": _hit_day(low_ret[:5], -5.0, "down"),
        "never_break_even_5d": 1 if max((value for value in high_ret[:5] if value is not None), default=-999.0) < 0.0 else 0,
        "never_break_even_10d": 1 if max((value for value in high_ret[:10] if value is not None), default=-999.0) < 0.0 else 0,
    }


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 4)


def _rate(values: Sequence[bool]) -> Optional[float]:
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 4)


def _bucket_match_score(target: Dict[str, Any], history: Dict[str, Any]) -> float:
    target_explain = target.get("explain_factors") or {}
    history_explain = history.get("explain_factors") or {}
    score = 0.0
    if str(target.get("sequence_label") or "") == str(history.get("sequence_label") or ""):
        score += 4.0
    if str(target.get("source_id") or "") == str(history.get("source_id") or ""):
        score += 3.0
    if _probe_strength_bucket(_safe_float(target_explain.get("probe_strength_score"))) == _probe_strength_bucket(_safe_float(history_explain.get("probe_strength_score"))):
        score += 2.0
    if _position_bucket(target_explain.get("price_position_20d")) == _position_bucket(history_explain.get("price_position_20d")):
        score += 2.0
    if _hot_rank_bucket(target_explain.get("hot_theme_best_rank")) == _hot_rank_bucket(history_explain.get("hot_theme_best_rank")):
        score += 1.0
    return score


def _numeric_distance(target_value: Any, history_value: Any, scale: float) -> float:
    return _normalize_feature_distance(_safe_float(target_value), _safe_float(history_value), scale)


def _history_distance(target: Dict[str, Any], history: Dict[str, Any], source_id: str) -> float:
    target_explain = target.get("explain_factors") or {}
    history_explain = history.get("explain_factors") or {}
    distance = 0.0
    distance += _numeric_distance(target_explain.get("probe_strength_score"), history_explain.get("probe_strength_score"), 12.0)
    distance += _numeric_distance(target_explain.get("oib_ratio"), history_explain.get("oib_ratio"), 0.08)
    distance += _numeric_distance(target_explain.get("same_day_pullback_ratio"), history_explain.get("same_day_pullback_ratio"), 0.18)
    distance += _numeric_distance(target_explain.get("price_position_20d"), history_explain.get("price_position_20d"), 0.16)
    distance += _numeric_distance(target_explain.get("buy_support_ratio"), history_explain.get("buy_support_ratio"), 0.45)
    distance += _numeric_distance(target_explain.get("support_pressure_spread"), history_explain.get("support_pressure_spread"), 0.16)
    distance += _numeric_distance(target_explain.get("hot_theme_best_rank"), history_explain.get("hot_theme_best_rank"), 18.0)
    if source_id == CONFIRM_SOURCE_ID:
        distance += _numeric_distance(target_explain.get("d3_oib_ratio"), history_explain.get("d3_oib_ratio"), 0.08)
        distance += _numeric_distance(target_explain.get("d3_l2_super_net_ratio"), history_explain.get("d3_l2_super_net_ratio"), 0.05)
        distance += _numeric_distance(target_explain.get("d3_l2_main_net_ratio"), history_explain.get("d3_l2_main_net_ratio"), 0.05)
        distance += _numeric_distance(target_explain.get("d3_support_pressure_spread"), history_explain.get("d3_support_pressure_spread"), 0.14)
    distance -= _bucket_match_score(target, history) * 0.35
    return round(distance, 6)


def _select_history_matches(
    target: Dict[str, Any],
    history_rows: Sequence[Dict[str, Any]],
    source_id: str,
) -> List[Dict[str, Any]]:
    target_sequence = str(target.get("sequence_label") or "")
    filtered = [
        item for item in history_rows
        if item.get("followthrough") is not None
        and (
            str(item.get("sequence_label") or "") == target_sequence
            or _bucket_match_score(target, item) >= 5.0
        )
    ]
    if len(filtered) < PROBE_MIN_HISTORY_SAMPLES:
        filtered = [item for item in history_rows if item.get("followthrough") is not None]
    ranked = sorted(
        filtered,
        key=lambda item: (
            _history_distance(target, item, source_id),
            item.get("trade_date") or "",
            item.get("symbol") or "",
        ),
    )
    return ranked[:PROBE_MAX_HISTORY_SAMPLES]


def _history_case_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    follow = row.get("followthrough") or {}
    return {
        "symbol": str(row.get("symbol") or "").lower(),
        "name": _clean_text(row.get("name"), str(row.get("symbol") or "").lower()),
        "trade_date": str(row.get("trade_date") or ""),
        "sequence_label": str(row.get("sequence_label") or ""),
        "close_5d_pct": _jsonable(follow.get("close_5d_pct")),
        "close_10d_pct": _jsonable(follow.get("close_10d_pct")),
        "max_high_10d_pct": _jsonable(follow.get("max_high_10d_pct")),
        "min_low_5d_pct": _jsonable(follow.get("min_low_5d_pct")),
        "hit_up5_day": follow.get("hit_up5_day"),
        "hit_down5_day": follow.get("hit_down5_day"),
    }


def _build_history_stat_summary(
    target: Dict[str, Any],
    matched_rows: Sequence[Dict[str, Any]],
    source_id: str,
) -> Dict[str, Any]:
    followups = [item["followthrough"] for item in matched_rows if item.get("followthrough") is not None]
    if not followups:
        return {
            "sample_count": 0,
            "summary_text": "历史同类样本还不够，先看事件本身，不要把研究期少量案例当统计结论。",
            "similar_cases": [],
        }

    close_1d = [item.get("close_1d_pct") for item in followups]
    close_3d = [item.get("close_3d_pct") for item in followups]
    close_5d = [item.get("close_5d_pct") for item in followups]
    close_10d = [item.get("close_10d_pct") for item in followups]
    avg_5d = _mean(close_5d)
    avg_10d = _mean(close_10d)
    up5_days = [int(item["hit_up5_day"]) for item in followups if item.get("hit_up5_day") is not None]
    hit_up5_day_mode = None
    if up5_days:
        hit_up5_day_mode = min(sorted(set(up5_days)), key=lambda day: (-up5_days.count(day), day))

    stats = {
        "sample_count": len(followups),
        "close_win_rate_1d": _rate([value is not None and value > 0 for value in close_1d if value is not None]),
        "close_win_rate_3d": _rate([value is not None and value > 0 for value in close_3d if value is not None]),
        "close_win_rate_5d": _rate([value is not None and value > 0 for value in close_5d if value is not None]),
        "close_win_rate_10d": _rate([value is not None and value > 0 for value in close_10d if value is not None]),
        "avg_return_5d_pct": avg_5d,
        "avg_return_10d_pct": avg_10d,
        "drawdown_hit_-3_5d_rate": _rate([item.get("hit_down3_day") is not None for item in followups]),
        "drawdown_hit_-5_5d_rate": _rate([item.get("hit_down5_day") is not None for item in followups]),
        "breakout_hit_+5_10d_rate": _rate([item.get("hit_up5_day") is not None for item in followups]),
        "breakout_hit_+8_10d_rate": _rate([item.get("hit_up8_day") is not None for item in followups]),
        "first_hit_+5_best_day": hit_up5_day_mode,
        "never_break_even_5d_rate": _rate([bool(item.get("never_break_even_5d")) for item in followups]),
        "never_break_even_10d_rate": _rate([bool(item.get("never_break_even_10d")) for item in followups]),
        "similar_cases": [_history_case_summary(item) for item in matched_rows[:PROBE_SIMILAR_CASE_LIMIT]],
        "group_label": _history_group_summary(
            str(target.get("sequence_label") or ""),
            _probe_strength_bucket(_safe_float((target.get("explain_factors") or {}).get("probe_strength_score"))),
            _position_bucket((target.get("explain_factors") or {}).get("price_position_20d")),
            source_id,
        ),
    }

    win5 = stats["close_win_rate_5d"]
    up5 = stats["breakout_hit_+5_10d_rate"]
    risk5 = stats["drawdown_hit_-5_5d_rate"]
    break_even = stats["never_break_even_10d_rate"]
    sequence_label = str(target.get("sequence_label") or "试盘")
    sample_count = stats["sample_count"]
    day_text = f"最常在第 {hit_up5_day_mode} 天摸到 +5%" if hit_up5_day_mode else "多数样本 10 日内都没摸到 +5%"
    stats["summary_text"] = (
        f"过去 {sample_count} 个{sequence_label}同类样本里，"
        f"5日内约有 {int(round((win5 or 0.0) * 100))}% 收盘能站上成本，"
        f"{int(round((up5 or 0.0) * 100))}% 会在10日内先冲到 +5%，"
        f"但也有 {int(round((risk5 or 0.0) * 100))}% 会在5日内先打到 -5%。"
        f"{day_text}。"
        f"若看回本能力，10日内最高价仍没回到成本上的比例约 {int(round((break_even or 0.0) * 100))}%。"
    )
    return stats


def _build_dynamic_history_stats(
    *,
    source_id: str,
    trade_date: str,
    symbol: str,
    name: str,
    sequence_label: str,
    explain_factors: Dict[str, Any],
    raw_payload: Dict[str, Any],
) -> Dict[str, Any]:
    cutoff_trade_date = _history_cutoff_trade_date(trade_date)
    history_rows = _load_probe_source_history(
        source_id,
        start_date=_history_window_start(cutoff_trade_date, 420),
        end_date=cutoff_trade_date,
        exclude_trade_date=trade_date,
    )
    enriched_history: List[Dict[str, Any]] = []
    for item in history_rows:
        explain = item.get("explain_factors") or {}
        payload = item.get("raw_payload") or {}
        history_sequence = str(payload.get("sequence_label") or explain.get("sequence_label") or "")
        followthrough = _load_daily_followthrough(str(item["symbol"]).lower(), str(item["trade_date"]))
        if followthrough is None:
            continue
        enriched_history.append(
            {
                **item,
                "sequence_label": history_sequence,
                "followthrough": followthrough,
            }
        )

    target = {
        "source_id": source_id,
        "trade_date": trade_date,
        "symbol": symbol.lower(),
        "name": name,
        "sequence_label": sequence_label,
        "explain_factors": explain_factors,
        "raw_payload": raw_payload,
    }
    matched_rows = _select_history_matches(target, enriched_history, source_id)
    stats = _build_history_stat_summary(target, matched_rows, source_id)
    stats.update(
        {
            "source_id": source_id,
            "trade_date": trade_date,
            "history_cutoff_trade_date": cutoff_trade_date,
            "uses_only_postclose_known_features": True,
            "future_window_completed_days": PROBE_FUTURE_WINDOW_DAYS,
        }
    )
    return stats


def _history_events_for_symbol(symbol: str, end_trade_date: str) -> List[Dict[str, Any]]:
    start_date = _history_window_start(end_trade_date, 120)
    index_map = _trade_date_index(start_date, end_trade_date)
    dates = list(index_map.keys())
    out: List[Dict[str, Any]] = []
    for date in dates:
        events = _day_events_cached(date)
        for item in events:
            if str(item["symbol"]).lower() == symbol and _is_probe_candidate(item):
                out.append(item)
    return out


def _classify_probe_sequence(symbol: str, trade_date: str) -> Tuple[int, str, Optional[int]]:
    history = _history_events_for_symbol(symbol, trade_date)
    index_map = _trade_date_index(_history_window_start(trade_date, 120), trade_date)
    sorted_events = sorted(history, key=lambda item: item["trade_date"])
    probe_index = 0
    last_probe_date: Optional[str] = None
    days_since_prev: Optional[int] = None
    role = "首次试盘"
    for item in sorted_events:
        if item["trade_date"] != trade_date:
            probe_index += 1
            last_probe_date = item["trade_date"]
            continue
        probe_index += 1
        days_since_prev = None if last_probe_date is None else _business_gap(index_map, last_probe_date, trade_date)
        if last_probe_date is None:
            role = "首次试盘"
        elif days_since_prev is not None and days_since_prev <= 5:
            role = "连续试盘"
        else:
            role = "重新试盘"
        return probe_index, role, days_since_prev
    return 1, "首次试盘", None


@lru_cache(maxsize=256)
def _day_events_cached(trade_date: str) -> Tuple[Dict[str, Any], ...]:
    rows = _build_day_events(trade_date)
    return tuple(rows)


def _watch_score(event: Dict[str, Any], feature_row: Optional[sqlite3.Row]) -> float:
    base = _probe_strength_score(event)
    hot_score = _safe_float(feature_row["hot_theme_score"]) if feature_row is not None else 0.0
    hot_bonus = min(max((hot_score - 50.0) / 20.0, 0.0), 1.0) * 8.0
    pos20 = _safe_float(feature_row["price_position_20d"]) if feature_row is not None else 1.0
    if pos20 <= 0:
        pos_bonus = 10.0
    elif pos20 <= 0.6:
        pos_bonus = 8.0
    elif pos20 <= 0.85:
        pos_bonus = 4.0
    else:
        pos_bonus = 0.0
    support_bonus = min(max((_safe_float(event.get("buy_support_ratio")) - 1.0) / 0.8, 0.0), 1.0) * 6.0
    cancel_bonus = min(max(_safe_float(event.get("cancel_sell_ratio")) / 0.001, 0.0), 1.0) * 4.0
    return round(base + hot_bonus + pos_bonus + support_bonus + cancel_bonus, 6)


def _confirm_score(event: Dict[str, Any], base_row: Optional[sqlite3.Row], d3_row: Optional[sqlite3.Row]) -> float:
    base = _probe_strength_score(event)
    if d3_row is None:
        return round(base, 6)
    d3_oib = _safe_float(d3_row["oib_ratio"])
    d3_super = _safe_float(d3_row["l2_super_net_ratio"])
    d3_main = _safe_float(d3_row["l2_main_net_ratio"])
    d3_hot = _safe_float(d3_row["hot_theme_score"])
    d3_pos20 = _safe_float(d3_row["price_position_20d"])
    confirm_bonus = 0.0
    if d3_oib > 0:
        confirm_bonus += 12.0
    if d3_super > 0:
        confirm_bonus += 12.0
    if d3_main > 0:
        confirm_bonus += 8.0
    if _safe_float(d3_row["support_pressure_spread"]) > 0:
        confirm_bonus += 6.0
    if _safe_float(d3_row["cancel_sell_ratio"]) >= 0.0003803886006703:
        confirm_bonus += 4.0
    if 0.4 <= d3_pos20 <= 0.7:
        confirm_bonus += 6.0
    elif d3_pos20 <= 0.85:
        confirm_bonus += 2.0
    hot_bonus = min(max((d3_hot - 60.0) / 20.0, 0.0), 1.0) * 8.0
    return round(base + confirm_bonus + hot_bonus, 6)


def _watch_risk_tags(event: Dict[str, Any], feature_row: Optional[sqlite3.Row]) -> List[str]:
    tags: List[str] = []
    if _safe_float(event.get("same_day_pullback_ratio")) > 0.85:
        tags.append("当天回吐偏大")
    if _safe_float(event.get("day_gap_pct")) > 4.0:
        tags.append("高开偏多")
    if feature_row is not None and _safe_float(feature_row["price_position_20d"]) > 0.9:
        tags.append("20日位置偏高")
    if feature_row is not None and _safe_float(feature_row["hot_theme_is_fading"]) > 0:
        tags.append("热点有退潮迹象")
    if int(_safe_float(event.get("touch_limit_up"))) == 1:
        tags.append("当日已触板，次日容易高开失真")
    return tags


def _confirm_risk_tags(base_row: Optional[sqlite3.Row], d3_row: Optional[sqlite3.Row]) -> List[str]:
    tags: List[str] = []
    if d3_row is None:
        return ["缺少D3确认数据"]
    if _safe_float(d3_row["oib_ratio"]) <= 0:
        tags.append("D3 OIB未转正")
    if _safe_float(d3_row["l2_super_net_ratio"]) <= 0:
        tags.append("D3超大单未继续流入")
    if _safe_float(d3_row["price_position_20d"]) > 0.9:
        tags.append("确认日位置偏高")
    if _safe_float(d3_row["hot_theme_is_fading"]) > 0:
        tags.append("确认日热点在走弱")
    if _safe_float(d3_row["market_broken_limit_up_ratio"]) > 0.38:
        tags.append("市场炸板率偏高")
    return tags


def _watch_reason_summary(event: Dict[str, Any], probe_index: int, sequence_label: str, feature_row: Optional[sqlite3.Row]) -> str:
    parts = [f"{sequence_label}"]
    if probe_index > 1:
        parts.append(f"第{probe_index}次试盘")
    parts.append("盘中急拉后没有直接发动")
    if _safe_float(event.get("same_day_pullback_ratio")) >= 0.45:
        parts.append("回吐明显，像在摸上方抛压")
    if _safe_float(event.get("oib_ratio")) >= 0.35:
        parts.append("主动推动偏强")
    if feature_row is not None and _safe_float(feature_row["hot_theme_best_rank"]) <= 30:
        parts.append("题材位置不差")
    return "；".join(parts[:4])


def _confirm_reason_summary(event: Dict[str, Any], probe_index: int, sequence_label: str, d3_row: Optional[sqlite3.Row]) -> str:
    parts = [f"{sequence_label}后进入D3确认"]
    if probe_index > 1:
        parts.append(f"这是第{probe_index}次试盘")
    if d3_row is not None:
        if _safe_float(d3_row["oib_ratio"]) > 0:
            parts.append("D3 OIB继续为正")
        if _safe_float(d3_row["l2_super_net_ratio"]) > 0:
            parts.append("超大单没有撤")
        if _safe_float(d3_row["support_pressure_spread"]) > 0:
            parts.append("盘口承接强于抛压")
        if _safe_float(d3_row["price_position_20d"]) <= 0.7:
            parts.append("位置还没顶到极限")
    return "；".join(parts[:5])


def _watch_action(event: Dict[str, Any], feature_row: Optional[sqlite3.Row]) -> Tuple[str, str, bool]:
    if int(_safe_float(event.get("touch_limit_up"))) == 1:
        return "watch", "观察", False
    if feature_row is not None and _safe_float(feature_row["price_position_20d"]) <= 0.65 and _safe_float(feature_row["hot_theme_best_rank"]) <= 20:
        return "watch", "重点观察", False
    return "watch", "观察", False


def _confirm_action(d3_row: Optional[sqlite3.Row]) -> Tuple[str, str, bool]:
    if d3_row is None:
        return "watch", "观察", False
    if _safe_float(d3_row["oib_ratio"]) > 0 and _safe_float(d3_row["l2_super_net_ratio"]) > 0:
        return "candidate_buy", "明日可买", True
    return "watch", "观察", False


def _history_hint_lines(history_stats: Dict[str, Any]) -> List[str]:
    sample_count = int(history_stats.get("sample_count") or 0)
    if sample_count <= 0:
        return [str(history_stats.get("summary_text") or "历史同类样本还不够，先按当前事件强弱做观察。")]
    return [
        str(history_stats.get("summary_text") or ""),
        f"样本数 {sample_count}；5日胜率 {int(round((_safe_float(history_stats.get('close_win_rate_5d')) or 0.0) * 100))}%；10日冲到 +5% 概率 {int(round((_safe_float(history_stats.get('breakout_hit_+5_10d_rate')) or 0.0) * 100))}%。",
        f"5日先打到 -5% 概率 {int(round((_safe_float(history_stats.get('drawdown_hit_-5_5d_rate')) or 0.0) * 100))}%；10日内没回到成本上的比例 {int(round((_safe_float(history_stats.get('never_break_even_10d_rate')) or 0.0) * 100))}%。",
    ]


def _history_explain_fields(history_stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "history_sample_count": int(history_stats.get("sample_count") or 0),
        "history_close_win_rate_1d": _jsonable(history_stats.get("close_win_rate_1d")),
        "history_close_win_rate_3d": _jsonable(history_stats.get("close_win_rate_3d")),
        "history_close_win_rate_5d": _jsonable(history_stats.get("close_win_rate_5d")),
        "history_close_win_rate_10d": _jsonable(history_stats.get("close_win_rate_10d")),
        "history_avg_return_5d_pct": _jsonable(history_stats.get("avg_return_5d_pct")),
        "history_avg_return_10d_pct": _jsonable(history_stats.get("avg_return_10d_pct")),
        "history_drawdown_hit_-3_5d_rate": _jsonable(history_stats.get("drawdown_hit_-3_5d_rate")),
        "history_drawdown_hit_-5_5d_rate": _jsonable(history_stats.get("drawdown_hit_-5_5d_rate")),
        "history_breakout_hit_+5_10d_rate": _jsonable(history_stats.get("breakout_hit_+5_10d_rate")),
        "history_breakout_hit_+8_10d_rate": _jsonable(history_stats.get("breakout_hit_+8_10d_rate")),
        "history_first_hit_+5_best_day": history_stats.get("first_hit_+5_best_day"),
        "history_never_break_even_5d_rate": _jsonable(history_stats.get("never_break_even_5d_rate")),
        "history_never_break_even_10d_rate": _jsonable(history_stats.get("never_break_even_10d_rate")),
        "history_group_label": _clean_text(history_stats.get("group_label")),
        "history_summary_text": _clean_text(history_stats.get("summary_text")),
        "history_similar_cases": history_stats.get("similar_cases") or [],
    }


def _standard_record(
    *,
    trade_date: str,
    symbol: str,
    name: str,
    source_id: str,
    source_name: str,
    source_version: str,
    rank: int,
    score: float,
    suggested_action: str,
    action_label: str,
    entry_allowed: bool,
    reason_summary: str,
    risk_tags: List[str],
    entry_block_reasons: List[str],
    explain_factors: Dict[str, Any],
    raw_payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "trade_date": str(trade_date),
        "symbol": symbol.lower(),
        "name": name,
        "source_id": source_id,
        "source_name": source_name,
        "source_type": "rule_strategy",
        "source_version": source_version,
        "artifact_version": source_version,
        "source_status": "active",
        "rank": int(rank),
        "score": round(float(score), 6),
        "score_scale": "raw",
        "horizon": "watch" if source_id == WATCH_SOURCE_ID else "swing",
        "suggested_action": suggested_action,
        "action_label": action_label,
        "entry_allowed": entry_allowed,
        "buy_rule": "D3确认池仅在确认日收盘后进入次日计划；观察池不直接给买点" if source_id == CONFIRM_SOURCE_ID else "当天先观察，重点看后续1到3日资金是否继续确认",
        "reason_summary": reason_summary,
        "risk_tags": risk_tags,
        "entry_block_reasons": entry_block_reasons,
        "explain_factors": explain_factors,
        "raw_payload": raw_payload,
        "artifact_path": "20260603-probe-lift-research",
    }


def generate_watch_candidates(trade_date: str, *, limit: int = WATCH_SOURCE_LIMIT) -> List[Dict[str, Any]]:
    events = list(_day_events_cached(trade_date))
    probe_events = [dict(item) for item in events if _is_probe_candidate(dict(item)) and not _is_launch_day(dict(item))]
    if not probe_events:
        return []
    symbols = sorted({str(item["symbol"]).lower() for item in probe_events})
    feature_lookup = _load_feature_rows(trade_date, symbols)
    name_lookup = _symbol_name_map(symbols, trade_date)
    rows: List[Dict[str, Any]] = []
    for item in probe_events:
        symbol = str(item["symbol"]).lower()
        feature_row = feature_lookup.get((symbol, trade_date))
        probe_index, sequence_label, days_since_prev = _classify_probe_sequence(symbol, trade_date)
        score = _watch_score(item, feature_row)
        suggested_action, action_label, entry_allowed = _watch_action(item, feature_row)
        risk_tags = _watch_risk_tags(item, feature_row)
        seed_explain_factors = {
            "probe_strength_score": _probe_strength_score(item),
            "probe_index": probe_index,
            "sequence_label": sequence_label,
            "same_day_pullback_ratio": _jsonable(item.get("same_day_pullback_ratio")),
            "oib_ratio": _jsonable(item.get("oib_ratio")),
            "amount_vs_day_median": _jsonable(item.get("amount_vs_day_median")),
            "buy_support_ratio": _jsonable(item.get("buy_support_ratio")),
            "support_pressure_spread": _jsonable(item.get("support_pressure_spread")),
            "price_position_20d": _jsonable(feature_row["price_position_20d"]) if feature_row is not None else None,
            "hot_theme_best_rank": _jsonable(feature_row["hot_theme_best_rank"]) if feature_row is not None else None,
            "hot_theme_score": _jsonable(feature_row["hot_theme_score"]) if feature_row is not None else None,
        }
        seed_raw_payload = {
            "signal_kind": "probe_watch",
            "probe_index": probe_index,
            "sequence_label": sequence_label,
            "days_since_prev_probe": days_since_prev,
            "event_time": _clean_text(item.get("event_time")),
            "business_anchor_time": _business_anchor_time(item),
            "probe_strength_score": _probe_strength_score(item),
            "observe_date": trade_date,
            "entry_signal_date": None,
            "entry_date": None,
            "event_fields": {key: _jsonable(value) for key, value in item.items()},
        }
        history_stats = _build_dynamic_history_stats(
            source_id=WATCH_SOURCE_ID,
            trade_date=trade_date,
            symbol=symbol,
            name=name_lookup.get(symbol, symbol),
            sequence_label=sequence_label,
            explain_factors=seed_explain_factors,
            raw_payload=seed_raw_payload,
        )
        explain_factors = {
            **seed_explain_factors,
            **_history_explain_fields(history_stats),
            "history_hint": _clean_text(history_stats.get("summary_text")),
        }
        raw_payload = {
            **seed_raw_payload,
            "historical_hint_lines": _history_hint_lines(history_stats),
            "historical_similar_stats": history_stats,
        }
        rows.append(
            _standard_record(
                trade_date=trade_date,
                symbol=symbol,
                name=name_lookup.get(symbol, symbol),
                source_id=WATCH_SOURCE_ID,
                source_name=WATCH_SOURCE_NAME,
                source_version=WATCH_SOURCE_VERSION,
                rank=0,
                score=score,
                suggested_action=suggested_action,
                action_label=action_label,
                entry_allowed=entry_allowed,
                reason_summary=_watch_reason_summary(item, probe_index, sequence_label, feature_row),
                risk_tags=risk_tags,
                entry_block_reasons=["观察池信号，先看后续1到3日资金是否继续确认"],
                explain_factors=explain_factors,
                raw_payload=raw_payload,
            )
        )
    ranked = sorted(rows, key=lambda item: (-float(item["score"]), item["symbol"]))[: int(limit)]
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx
    return ranked


def _find_prior_probe_date(symbol: str, confirm_trade_date: str) -> Optional[str]:
    start_date = _history_window_start(confirm_trade_date, 30)
    index_map = _trade_date_index(start_date, confirm_trade_date)
    dates = list(index_map.keys())
    prior: Optional[str] = None
    for date in dates:
        if date >= confirm_trade_date:
            break
        events = _day_events_cached(date)
        for item in events:
            if str(item["symbol"]).lower() == symbol and _is_probe_candidate(dict(item)) and not _is_launch_day(dict(item)):
                prior = date
    return prior


def generate_confirmed_candidates(trade_date: str, *, limit: int = CONFIRM_SOURCE_LIMIT) -> List[Dict[str, Any]]:
    probe_candidate_date = _prev_trade_date(_prev_trade_date(_prev_trade_date(trade_date) or "") or "")
    if not probe_candidate_date:
        return []
    probe_events = list(_day_events_cached(probe_candidate_date))
    candidate_symbols = sorted(
        {
            str(item["symbol"]).lower()
            for item in probe_events
            if _is_probe_candidate(dict(item)) and not _is_launch_day(dict(item))
        }
    )
    if not candidate_symbols:
        return []
    conn = _connect(FEATURE_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_confirm_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_confirm_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_confirm_symbols(symbol) VALUES (?)", [(symbol,) for symbol in candidate_symbols])
        d3_rows = conn.execute(
            """
            SELECT *
            FROM model_feature_daily_v1
            WHERE trade_date = ?
              AND symbol IN (SELECT symbol FROM temp_probe_confirm_symbols)
            """,
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    if not d3_rows:
        return []
    d3_lookup = {str(row["symbol"]).lower(): row for row in d3_rows}
    names = _symbol_name_map(candidate_symbols, trade_date)
    rows: List[Dict[str, Any]] = []
    for symbol in candidate_symbols:
        probe_date = _find_prior_probe_date(symbol, trade_date)
        if not probe_date:
            continue
        gap_index = _trade_date_index(_history_window_start(trade_date, 30), trade_date)
        gap = _business_gap(gap_index, probe_date, trade_date)
        if gap != 3:
            continue
        probe_event: Optional[Dict[str, Any]] = None
        for item in _day_events_cached(probe_date):
            if str(item["symbol"]).lower() == symbol and _is_probe_candidate(dict(item)) and not _is_launch_day(dict(item)):
                probe_event = dict(item)
                break
        if probe_event is None:
            continue
        d3_row = d3_lookup.get(symbol)
        if d3_row is None:
            continue
        if _safe_float(d3_row["oib_ratio"]) <= 0 and _safe_float(d3_row["l2_super_net_ratio"]) <= 0:
            continue
        probe_index, sequence_label, days_since_prev = _classify_probe_sequence(symbol, probe_date)
        score = _confirm_score(probe_event, None, d3_row)
        suggested_action, action_label, entry_allowed = _confirm_action(d3_row)
        risk_tags = _confirm_risk_tags(None, d3_row)
        seed_explain_factors = {
            "probe_strength_score": _probe_strength_score(probe_event),
            "probe_index": probe_index,
            "sequence_label": sequence_label,
            "d3_oib_ratio": _jsonable(d3_row["oib_ratio"]),
            "d3_l2_super_net_ratio": _jsonable(d3_row["l2_super_net_ratio"]),
            "d3_l2_main_net_ratio": _jsonable(d3_row["l2_main_net_ratio"]),
            "d3_support_pressure_spread": _jsonable(d3_row["support_pressure_spread"]),
            "d3_cancel_sell_ratio": _jsonable(d3_row["cancel_sell_ratio"]),
            "price_position_20d": _jsonable(d3_row["price_position_20d"]),
            "hot_theme_best_rank": _jsonable(d3_row["hot_theme_best_rank"]),
            "hot_theme_score": _jsonable(d3_row["hot_theme_score"]),
            "oib_ratio": _jsonable(probe_event.get("oib_ratio")),
            "same_day_pullback_ratio": _jsonable(probe_event.get("same_day_pullback_ratio")),
            "buy_support_ratio": _jsonable(probe_event.get("buy_support_ratio")),
            "support_pressure_spread": _jsonable(probe_event.get("support_pressure_spread")),
        }
        seed_raw_payload = {
            "signal_kind": "probe_d3_confirmed",
            "probe_trade_date": probe_date,
            "confirm_trade_date": trade_date,
            "probe_index": probe_index,
            "sequence_label": sequence_label,
            "days_since_prev_probe": days_since_prev,
            "observe_date": probe_date,
            "entry_signal_date": trade_date,
            "entry_date": _next_trade_date(trade_date) if entry_allowed else None,
            "event_fields": {key: _jsonable(value) for key, value in probe_event.items()},
            "confirm_fields": {key: _jsonable(d3_row[key]) for key in d3_row.keys()},
        }
        history_stats = _build_dynamic_history_stats(
            source_id=CONFIRM_SOURCE_ID,
            trade_date=trade_date,
            symbol=symbol,
            name=names.get(symbol, symbol),
            sequence_label=sequence_label,
            explain_factors=seed_explain_factors,
            raw_payload=seed_raw_payload,
        )
        explain_factors = {
            **seed_explain_factors,
            **_history_explain_fields(history_stats),
            "history_hint": _clean_text(history_stats.get("summary_text")),
        }
        raw_payload = {
            **seed_raw_payload,
            "historical_hint_lines": _history_hint_lines(history_stats),
            "historical_similar_stats": history_stats,
        }
        block_reasons = [] if entry_allowed else ["D3确认还不够硬，继续观察"]
        rows.append(
            _standard_record(
                trade_date=trade_date,
                symbol=symbol,
                name=names.get(symbol, symbol),
                source_id=CONFIRM_SOURCE_ID,
                source_name=CONFIRM_SOURCE_NAME,
                source_version=CONFIRM_SOURCE_VERSION,
                rank=0,
                score=score,
                suggested_action=suggested_action,
                action_label=action_label,
                entry_allowed=entry_allowed,
                reason_summary=_confirm_reason_summary(probe_event, probe_index, sequence_label, d3_row),
                risk_tags=risk_tags,
                entry_block_reasons=block_reasons,
                explain_factors=explain_factors,
                raw_payload=raw_payload,
            )
        )
    ranked = sorted(rows, key=lambda item: (-float(item["score"]), item["symbol"]))[: int(limit)]
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx
    return ranked


def generate_daily_candidates(source_id: str, trade_date: str, *, limit: int) -> List[Dict[str, Any]]:
    if source_id == WATCH_SOURCE_ID:
        return generate_watch_candidates(trade_date, limit=limit)
    if source_id == CONFIRM_SOURCE_ID:
        return generate_confirmed_candidates(trade_date, limit=limit)
    raise ValueError(f"unsupported probe source: {source_id}")
