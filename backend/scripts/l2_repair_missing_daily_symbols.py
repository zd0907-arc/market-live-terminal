"""
按 archive 中存在、但 history_daily_l2 尚缺失的 symbol-day 做定向回补。

适用于：
- 某一天因为 staging 不完整、worker 未覆盖全量 symbol、半途失败等原因，
  导致正式日表存在大面积缺口；
- 希望只补缺失 symbol，不重跑整天全量。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_daily_backfill import REQUIRED_FILES, backfill_day_package, canonical_trade_date


ARCHIVE_SYMBOL_RE_TEMPLATE = r"^{day}/([0-9]{{6}}\.(?:SZ|SH|BJ))/$"


def _get_db_path(explicit_db_path: str = "") -> str:
    return explicit_db_path or os.getenv("DB_PATH") or os.path.join(ROOT_DIR, "data", "market_data.db")


def _symbol_to_vendor_dir(symbol: str) -> str:
    text = (symbol or "").strip().lower()
    return f"{text[2:]}.{text[:2].upper()}"


def list_missing_daily_symbols(month_root: Path, db_path: str, trade_date: str) -> List[str]:
    compact = trade_date.replace("-", "")
    archive_path = Path(month_root) / compact[:6] / f"{compact}.7z"
    listing = subprocess.run(["tar", "-tf", str(archive_path)], capture_output=True, text=True)
    if listing.returncode != 0:
        raise RuntimeError(f"读取 archive 失败: {archive_path} :: {listing.stderr.strip()}")
    pat = re.compile(ARCHIVE_SYMBOL_RE_TEMPLATE.format(day=compact), re.I)
    archive_symbols = {
        match.group(1).split(".")[1].lower() + match.group(1).split(".")[0]
        for line in listing.stdout.splitlines()
        for match in [pat.match(line.strip())]
        if match
    }

    conn = sqlite3.connect(db_path)
    try:
        db_symbols = {
            str(row[0]) for row in conn.execute("SELECT symbol FROM history_daily_l2 WHERE date=?", (trade_date,))
        }
    finally:
        conn.close()

    return sorted(archive_symbols - db_symbols)


def extract_symbols(archive_path: Path, trade_date: str, symbols: Sequence[str], stage_root: Path) -> Path:
    compact = trade_date.replace("-", "")
    day_dir = stage_root / compact
    if day_dir.exists():
        shutil.rmtree(day_dir)
    stage_root.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        vendor = _symbol_to_vendor_dir(symbol)
        members = [f"{compact}/{vendor}/{name}" for name in REQUIRED_FILES]
        result = subprocess.run(
            ["tar", "-xf", str(archive_path), "-C", str(stage_root), *members],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"抽取失败: {archive_path} :: {vendor} :: {result.stderr.strip()}")
    return day_dir


def repair_missing_daily_symbols(
    month_root: Path,
    db_path: str,
    stage_root: Path,
    trade_dates: Sequence[str],
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
    cleanup: bool = True,
) -> Dict[str, object]:
    reports: List[Dict[str, object]] = []
    for trade_date in trade_dates:
        trade_date = canonical_trade_date(trade_date)
        missing_symbols = list_missing_daily_symbols(month_root=month_root, db_path=db_path, trade_date=trade_date)
        compact = trade_date.replace("-", "")
        archive_path = Path(month_root) / compact[:6] / f"{compact}.7z"
        if not missing_symbols:
            reports.append({"trade_date": trade_date, "missing_symbols": 0, "report": None})
            continue
        day_dir = extract_symbols(archive_path=archive_path, trade_date=trade_date, symbols=missing_symbols, stage_root=stage_root)
        try:
            report = backfill_day_package(
                day_dir,
                symbols=missing_symbols,
                large_threshold=large_threshold,
                super_threshold=super_threshold,
                mode=f"repair_missing_{compact}",
                dry_run=False,
            )
            reports.append(
                {
                    "trade_date": trade_date,
                    "missing_symbols": len(missing_symbols),
                    "report": report,
                }
            )
        finally:
            if cleanup and day_dir.exists():
                shutil.rmtree(day_dir)

    return {
        "trade_dates": list(trade_dates),
        "reports": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="定向修复 history_daily_l2 缺失的 symbol-day")
    parser.add_argument("--month-root", required=True, help=r"原始包根目录，如 D:\MarketData")
    parser.add_argument("--db-path", default="", help="正式库路径")
    parser.add_argument("--stage-root", required=True, help=r"临时解压目录，如 Z:\l2_repair_missing")
    parser.add_argument("--trade-dates", required=True, help="逗号分隔 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    db_path = _get_db_path(args.db_path)
    os.environ["DB_PATH"] = db_path
    trade_dates = [item.strip() for item in args.trade_dates.split(",") if item.strip()]

    report = repair_missing_daily_symbols(
        month_root=Path(args.month_root),
        db_path=db_path,
        stage_root=Path(args.stage_root),
        trade_dates=trade_dates,
        cleanup=not bool(args.no_cleanup),
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[l2-repair-missing-daily] days={len(report['reports'])}")
        for item in report["reports"]:
            sub = item.get("report")
            if not sub:
                print(f"  - trade_date={item['trade_date']} missing=0")
                continue
            print(
                f"  - trade_date={item['trade_date']} missing={item['missing_symbols']} "
                f"success={sub['success_symbols']} failed={sub['failed_symbols']} empty={sub.get('empty_symbols', 0)}"
            )


if __name__ == "__main__":
    main()
