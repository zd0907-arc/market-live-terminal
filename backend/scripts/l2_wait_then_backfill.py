"""
等待指定交易日回补完成后，自动清理解压目录并顺跑剩余日包。

适合场景：
- 某个大日包已在 Windows 上手动/前序任务启动
- 想在它完成后自动接着跑剩余日期，避免人工盯守
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_month_backfill import backfill_month_archives, _cleanup_day_dir


def _get_db_path(explicit_db_path: str = "") -> str:
    return explicit_db_path or os.getenv("DB_PATH") or os.path.join(ROOT_DIR, "data", "market_data.db")


def wait_for_trade_date_completion(
    trade_date: str,
    db_path: str,
    poll_seconds: int = 60,
    timeout_seconds: int = 0,
) -> Dict[str, object]:
    started = time.time()
    while True:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT id, trade_date, status, symbol_count, rows_5m, rows_daily, message
                FROM l2_daily_ingest_runs
                WHERE trade_date=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (trade_date,),
            ).fetchone()
        finally:
            conn.close()

        if row and row[2] != "running":
            return {
                "run_id": row[0],
                "trade_date": row[1],
                "status": row[2],
                "symbol_count": row[3],
                "rows_5m": row[4],
                "rows_daily": row[5],
                "message": row[6],
                "wait_seconds": int(time.time() - started),
            }

        if timeout_seconds > 0 and time.time() - started >= timeout_seconds:
            raise TimeoutError(f"等待超时：{trade_date} 仍未结束")

        time.sleep(max(5, poll_seconds))


def wait_then_backfill(
    wait_trade_date: str,
    month_dir: Path,
    days: Optional[Sequence[str]] = None,
    db_path: str = "",
    poll_seconds: int = 60,
    cleanup_wait_day_dir: bool = True,
    cleanup_extracted: bool = True,
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
    mode: str = "wait_then_batch",
) -> Dict[str, object]:
    resolved_db_path = _get_db_path(db_path)
    os.environ["DB_PATH"] = resolved_db_path

    wait_result = wait_for_trade_date_completion(
        trade_date=wait_trade_date,
        db_path=resolved_db_path,
        poll_seconds=poll_seconds,
    )

    if cleanup_wait_day_dir:
        _cleanup_day_dir(Path(month_dir) / wait_trade_date)

    remaining_days = [day for day in (list(days) if days else []) if day != wait_trade_date]
    month_report = backfill_month_archives(
        Path(month_dir),
        days=remaining_days or None,
        symbols=None,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
        mode=mode,
        dry_run=False,
        cleanup_extracted=cleanup_extracted,
    )

    return {
        "wait_trade_date": wait_trade_date,
        "wait_result": wait_result,
        "month_report": month_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="等待某日回补完成后，继续顺跑剩余日包")
    parser.add_argument("wait_trade_date", help="等待中的交易日，格式 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("month_dir", help=r"月份目录，如 D:\MarketData\202603")
    parser.add_argument("--days", default="", help="逗号分隔的 YYYYMMDD，包含等待日与剩余日均可")
    parser.add_argument("--db-path", default="", help="正式库路径")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--no-cleanup-wait-day", action="store_true", help="等待日完成后不删除其解压目录")
    parser.add_argument("--no-cleanup-extracted", action="store_true", help="后续日包回补完成后不删除解压目录")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--mode", default="wait_then_batch")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    wait_trade_date = args.wait_trade_date
    if len(wait_trade_date) == 8 and wait_trade_date.isdigit():
        wait_trade_date = f"{wait_trade_date[:4]}-{wait_trade_date[4:6]}-{wait_trade_date[6:]}"

    days = [item.strip() for item in args.days.split(",") if item.strip()]
    report = wait_then_backfill(
        wait_trade_date=wait_trade_date,
        month_dir=Path(args.month_dir),
        days=days or None,
        db_path=args.db_path,
        poll_seconds=int(args.poll_seconds),
        cleanup_wait_day_dir=not bool(args.no_cleanup_wait_day),
        cleanup_extracted=not bool(args.no_cleanup_extracted),
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
        mode=args.mode,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-wait-then-backfill] wait_trade_date={report['wait_trade_date']} "
            f"wait_status={report['wait_result']['status']} "
            f"remaining_days={len(report['month_report']['days'])}"
        )


if __name__ == "__main__":
    main()
