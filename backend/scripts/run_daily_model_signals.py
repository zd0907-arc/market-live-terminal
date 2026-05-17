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

from backend.app.services.selection_daily_workbench import run_daily_selection_sources
from backend.app.db.selection_db import ensure_selection_schema, get_selection_connection


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
    parser = argparse.ArgumentParser(description="Run daily selection candidate sources into the unified workbench tables")
    parser.add_argument("--date", default="", help="Signal date YYYY-MM-DD")
    parser.add_argument("--start-date", default="", help="Backfill start date YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="Backfill end date YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--sources", default="", help="Comma separated source ids. Default: all P1 sources.")
    args = parser.parse_args(argv)

    if args.date and (args.start_date or args.end_date):
        raise SystemExit("--date 不能和 --start-date/--end-date 同时使用")
    if not args.date and not (args.start_date and args.end_date):
        raise SystemExit("必须提供 --date，或同时提供 --start-date 与 --end-date")

    source_ids = [item.strip() for item in args.sources.split(",") if item.strip()] or None
    if args.date:
        payload = run_daily_selection_sources(args.date, limit=int(args.limit), source_ids=source_ids)
    else:
        dates = _feature_trade_dates(args.start_date, args.end_date)
        results = [
            run_daily_selection_sources(trade_date, limit=int(args.limit), source_ids=source_ids)
            for trade_date in dates
        ]
        payload = {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "trade_dates": len(dates),
            "results": results,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
