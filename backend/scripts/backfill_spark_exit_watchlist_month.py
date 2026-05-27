from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_candidate_store import replace_daily_exit_watchlist
from backend.app.services.spark_opportunity_exit import get_daily_exit_watchlist
from backend.app.db.selection_db import get_selection_connection


def _trade_dates_for_month(month: str) -> List[str]:
    start = datetime.strptime(f"{month}-01", "%Y-%m-%d")
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)
    conn = get_selection_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM selection_feature_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date ASC
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()
        return [str(row["trade_date"]) for row in rows]
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Spark exit watchlist rows for one month.")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format, e.g. 2026-05")
    args = parser.parse_args()

    trade_dates = _trade_dates_for_month(args.month)
    if not trade_dates:
        print(f"[spark-exit-backfill] no trade dates found for {args.month}")
        return

    total_rows = 0
    for trade_date in trade_dates:
        payload = get_daily_exit_watchlist(trade_date, use_cache=False)
        count = replace_daily_exit_watchlist(trade_date, payload)
        total_rows += int(count)
        print(f"[spark-exit-backfill] {trade_date}: {count} rows")
    print(f"[spark-exit-backfill] done month={args.month} trade_dates={len(trade_dates)} total_rows={total_rows}")


if __name__ == "__main__":
    main()
