#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.selection_db import ensure_selection_schema, get_selection_connection  # noqa: E402
from backend.app.services.probe_signal_selector import CONFIRM_SOURCE_ID, WATCH_SOURCE_ID  # noqa: E402
from backend.app.services.selection_daily_workbench import run_daily_selection_sources  # noqa: E402
from backend.scripts.export_probe_signal_research_payload import build_payload  # noqa: E402


def _feature_trade_dates(start_date: str, end_date: str) -> list[str]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM selection_feature_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return [str(row["trade_date"]) for row in rows]
    finally:
        conn.close()


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Build probe signal historical similar stats and optional research payload")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--sources", default=f"{WATCH_SOURCE_ID},{CONFIRM_SOURCE_ID}")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--export-payload", action="store_true")
    parser.add_argument("--payload-out", default=str(ROOT / "public/research/probe_signal_research_payload.json"))
    parser.add_argument("--payload-limit-per-source", type=int, default=24)
    args = parser.parse_args(argv)

    source_ids = [item.strip() for item in str(args.sources or "").split(",") if item.strip()]
    dates = _feature_trade_dates(str(args.start_date), str(args.end_date))
    backfill_results = []
    if not args.skip_backfill:
        for trade_date in dates:
            payload = run_daily_selection_sources(
                trade_date,
                limit=int(args.limit),
                source_ids=source_ids,
                include_exit_watchlist=False,
            )
            backfill_results.append(
                {
                    "trade_date": trade_date,
                    "sources": payload.get("sources") or {},
                    "errors": payload.get("errors") or {},
                    "merged_count": payload.get("merged_count") or 0,
                }
            )

    payload_meta = None
    if args.export_payload:
        payload = build_payload(str(args.start_date), str(args.end_date), int(args.payload_limit_per_source))
        out_path = Path(args.payload_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload_meta = {"out": str(out_path), "sections": {item["id"]: item["stock_count"] for item in payload["sections"]}}

    print(
        json.dumps(
            {
                "start_date": args.start_date,
                "end_date": args.end_date,
                "source_ids": source_ids,
                "trade_dates": len(dates),
                "backfill_results": backfill_results,
                "payload": payload_meta,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
