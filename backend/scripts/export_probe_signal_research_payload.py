#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.probe_signal_selector import (  # noqa: E402
    CONFIRM_SOURCE_ID,
    WATCH_SOURCE_ID,
    _connect,
    _history_window_start,
    _jsonable,
    _load_daily_followthrough,
    _safe_float,
)
from backend.app.core.config import RESEARCH_CURRENT_ROOT  # noqa: E402
from backend.app.db.selection_db import get_selection_connection  # noqa: E402


RESEARCH_ROOT = Path(RESEARCH_CURRENT_ROOT)
ATOMIC_DB = RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
OUT_PATH = ROOT / "public/research/probe_signal_research_payload.json"
WINDOW_BEFORE_DAYS = 45
WINDOW_AFTER_DAYS = 45


def _selection_source_rows(
    start_date: str,
    end_date: str,
    source_ids: Sequence[str],
    limit_per_source: int,
) -> List[Dict[str, Any]]:
    conn = get_selection_connection()
    try:
        placeholders = ",".join("?" for _ in source_ids)
        rows = conn.execute(
            f"""
            SELECT trade_date, symbol, name, source_id, source_name, rank, score, explain_factors_json, raw_payload_json
            FROM selection_candidate_sources
            WHERE trade_date >= ?
              AND trade_date <= ?
              AND source_id IN ({placeholders})
            ORDER BY trade_date DESC, source_id ASC, rank ASC
            """,
            [start_date, end_date, *source_ids],
        ).fetchall()
    finally:
        conn.close()

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = str(row["source_id"])
        explain = json.loads(str(row["explain_factors_json"] or "{}"))
        raw = json.loads(str(row["raw_payload_json"] or "{}"))
        grouped[key].append(
            {
                "trade_date": str(row["trade_date"]),
                "symbol": str(row["symbol"]).lower(),
                "name": str(row["name"] or row["symbol"]),
                "source_id": key,
                "source_name": str(row["source_name"] or key),
                "rank": int(row["rank"] or 0),
                "score": round(_safe_float(row["score"]), 4),
                "explain_factors": explain if isinstance(explain, dict) else {},
                "raw_payload": raw if isinstance(raw, dict) else {},
            }
        )

    result: List[Dict[str, Any]] = []
    for source_id in source_ids:
        result.extend(grouped.get(source_id, [])[:limit_per_source])
    return sorted(result, key=lambda item: (item["source_id"], item["trade_date"], item["rank"], item["symbol"]))


def _trade_calendar(start_date: str, end_date: str) -> List[str]:
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


def _date_offset(calendar: Sequence[str], anchor: str, offset: int) -> Optional[str]:
    try:
        idx = list(calendar).index(anchor)
    except ValueError:
        return None
    target = idx + int(offset)
    if target < 0 or target >= len(calendar):
        return None
    return list(calendar)[target]


def _load_bars(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT symbol, trade_date, open, high, low, close, total_amount, total_volume,
                   l2_main_net_amount, l2_super_net_amount, l1_main_net_amount, l1_super_net_amount
            FROM atomic_trade_daily
            WHERE symbol = ?
              AND trade_date >= ?
              AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (symbol.lower(), start_date, end_date),
        ).fetchall()
        return [
            {
                "trade_date": str(row["trade_date"]),
                "open": round(_safe_float(row["open"]), 4),
                "high": round(_safe_float(row["high"]), 4),
                "low": round(_safe_float(row["low"]), 4),
                "close": round(_safe_float(row["close"]), 4),
                "total_amount": round(_safe_float(row["total_amount"]), 2),
                "total_volume": round(_safe_float(row["total_volume"]), 2),
                "l2_main_net_amount": round(_safe_float(row["l2_main_net_amount"]), 2),
                "l2_super_net_amount": round(_safe_float(row["l2_super_net_amount"]), 2),
                "l1_main_net_amount": round(_safe_float(row["l1_main_net_amount"]), 2),
                "l1_super_net_amount": round(_safe_float(row["l1_super_net_amount"]), 2),
            }
            for row in rows
        ]
    finally:
        conn.close()


def _card_item(row: Dict[str, Any], calendar: Sequence[str]) -> Dict[str, Any]:
    trade_date = str(row["trade_date"])
    symbol = str(row["symbol"]).lower()
    explain = row["explain_factors"] or {}
    raw = row["raw_payload"] or {}
    start_date = _date_offset(calendar, trade_date, -WINDOW_BEFORE_DAYS) or _history_window_start(trade_date, 90)
    end_date = _date_offset(calendar, trade_date, WINDOW_AFTER_DAYS) or trade_date
    bars = _load_bars(symbol, start_date, end_date)
    follow = _load_daily_followthrough(symbol, trade_date) or {}
    history_stats = raw.get("historical_similar_stats") if isinstance(raw.get("historical_similar_stats"), dict) else {}
    return {
        "id": f"{row['source_id']}_{trade_date}_{symbol}",
        "symbol": symbol,
        "name": row["name"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "trade_date": trade_date,
        "probe_type": raw.get("sequence_label") or explain.get("sequence_label") or "",
        "signal_kind": raw.get("signal_kind") or "",
        "score": row["score"],
        "history_sample_count": int(history_stats.get("sample_count") or explain.get("history_sample_count") or 0),
        "history_summary_text": history_stats.get("summary_text") or explain.get("history_summary_text") or "",
        "history_close_win_rate_5d": _jsonable(history_stats.get("close_win_rate_5d") or explain.get("history_close_win_rate_5d")),
        "history_avg_return_5d_pct": _jsonable(history_stats.get("avg_return_5d_pct") or explain.get("history_avg_return_5d_pct")),
        "history_breakout_hit_+5_10d_rate": _jsonable(history_stats.get("breakout_hit_+5_10d_rate") or explain.get("history_breakout_hit_+5_10d_rate")),
        "history_breakout_hit_+8_10d_rate": _jsonable(history_stats.get("breakout_hit_+8_10d_rate") or explain.get("history_breakout_hit_+8_10d_rate")),
        "history_drawdown_hit_-5_5d_rate": _jsonable(history_stats.get("drawdown_hit_-5_5d_rate") or explain.get("history_drawdown_hit_-5_5d_rate")),
        "history_first_hit_+5_best_day": history_stats.get("first_hit_+5_best_day") or explain.get("history_first_hit_+5_best_day"),
        "history_similar_cases": history_stats.get("similar_cases") or explain.get("history_similar_cases") or [],
        "probe_strength_score": _jsonable(explain.get("probe_strength_score")),
        "oib_ratio": _jsonable(explain.get("oib_ratio")),
        "same_day_pullback_ratio": _jsonable(explain.get("same_day_pullback_ratio")),
        "price_position_20d": _jsonable(explain.get("price_position_20d")),
        "hot_theme_best_rank": _jsonable(explain.get("hot_theme_best_rank")),
        "realized_close_5d_pct": _jsonable(follow.get("close_5d_pct")),
        "realized_close_10d_pct": _jsonable(follow.get("close_10d_pct")),
        "realized_max_high_10d_pct": _jsonable(follow.get("max_high_10d_pct")),
        "realized_min_low_5d_pct": _jsonable(follow.get("min_low_5d_pct")),
        "bars": bars,
        "window": {
            "start_date": bars[0]["trade_date"] if bars else start_date,
            "end_date": bars[-1]["trade_date"] if bars else end_date,
            "actual_bars": len(bars),
        },
    }


def build_payload(start_date: str, end_date: str, limit_per_source: int) -> Dict[str, Any]:
    rows = _selection_source_rows(start_date, end_date, [WATCH_SOURCE_ID, CONFIRM_SOURCE_ID], limit_per_source)
    calendar = _trade_calendar(_history_window_start(start_date, 120), end_date)
    sections = []
    for source_id, title, description in (
        (WATCH_SOURCE_ID, "试盘观察池", "当天盘后识别到的试盘样本，重点看像不像在测抛压。"),
        (CONFIRM_SOURCE_ID, "试盘D3确认池", "试盘后第3日仍有资金确认的样本，重点看后续冲高兑现。"),
    ):
        items = [_card_item(row, calendar) for row in rows if row["source_id"] == source_id]
        sections.append(
            {
                "id": source_id,
                "title": title,
                "description": description,
                "source_signal_count": len(items),
                "stock_count": len(items),
                "items": items,
            }
        )
    return {
        "meta": {
            "title": "试盘事件研究页",
            "start_date": start_date,
            "end_date": end_date,
            "window_rule": "每张图按信号日前 45 个交易日 + 信号日后 45 个交易日取窗口；图上显示日K、成交量、主力净流入和超大单净流入。",
            "source": "selection_candidate_sources + atomic_trade_daily",
        },
        "sections": sections,
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Export probe signal research page payload")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--limit-per-source", type=int, default=24)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args(argv)

    payload = build_payload(str(args.start_date), str(args.end_date), int(args.limit_per_source))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out_path), "sections": {item["id"]: item["stock_count"] for item in payload["sections"]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
