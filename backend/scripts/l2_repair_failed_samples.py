"""
按失败表记录，定向修复盘后 L2 日级回补中的失败样本。

当前主要用于：
- 对历史 `OrderID 无法在逐笔委托中对齐` 的 symbol-day 做定向重跑；
- 只从 `.7z` 原始包中抽取失败 symbol 的三个 CSV，避免整日全量重新解压。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_daily_backfill import backfill_day_package


REQUIRED_FILES = ("行情.csv", "逐笔成交.csv", "逐笔委托.csv")


def _get_db_path(explicit_db_path: str = "") -> str:
    return explicit_db_path or os.getenv("DB_PATH") or os.path.join(ROOT_DIR, "data", "market_data.db")


def _symbol_to_vendor_dir(symbol: str) -> str:
    text = (symbol or "").strip().lower()
    if len(text) != 8 or not text.startswith(("sh", "sz", "bj")):
        raise ValueError(f"无效 symbol: {symbol}")
    market = text[:2].upper()
    code = text[2:]
    return f"{code}.{market}"


def query_failed_symbols(
    db_path: str,
    failure_like: str,
    trade_dates: Optional[Sequence[str]] = None,
) -> Dict[str, List[str]]:
    conn = sqlite3.connect(db_path)
    try:
        sql = """
        SELECT DISTINCT trade_date, symbol
        FROM l2_daily_ingest_failures
        WHERE error_message LIKE ?
        """
        params: List[str] = [failure_like]
        if trade_dates:
            placeholders = ",".join("?" for _ in trade_dates)
            sql += f" AND trade_date IN ({placeholders})"
            params.extend(trade_dates)
        sql += " ORDER BY trade_date, symbol"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    grouped: DefaultDict[str, List[str]] = defaultdict(list)
    for trade_date, symbol in rows:
        grouped[str(trade_date)].append(str(symbol))
    return dict(grouped)


def extract_symbol_files_from_archive(
    archive_path: Path,
    trade_date_raw: str,
    symbols: Sequence[str],
    stage_root: Path,
) -> Path:
    trade_date_compact = trade_date_raw.replace("-", "")
    day_dir = stage_root / trade_date_compact
    if day_dir.exists():
        shutil.rmtree(day_dir)
    stage_root.mkdir(parents=True, exist_ok=True)

    members: List[str] = []
    for symbol in symbols:
        vendor_dir = _symbol_to_vendor_dir(symbol)
        for name in REQUIRED_FILES:
            members.append(f"{trade_date_compact}/{vendor_dir}/{name}")

    cmd = ["tar", "-xf", str(archive_path), "-C", str(stage_root), *members]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"解压失败: {archive_path} :: {result.stderr.strip()}")
    if not day_dir.is_dir():
        raise RuntimeError(f"未解压出目标日目录: {day_dir}")
    return day_dir


def repair_failed_samples(
    month_root: Path,
    db_path: str,
    stage_root: Path,
    failure_like: str = "OrderID 无法%",
    trade_dates: Optional[Sequence[str]] = None,
    cleanup: bool = True,
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
) -> Dict[str, object]:
    grouped = query_failed_symbols(db_path=db_path, failure_like=failure_like, trade_dates=trade_dates)
    reports: List[Dict[str, object]] = []

    for trade_date, symbols in grouped.items():
        compact = trade_date.replace("-", "")
        archive_path = Path(month_root) / compact[:6] / f"{compact}.7z"
        if not archive_path.is_file():
            raise FileNotFoundError(f"缺少原始包: {archive_path}")

        day_dir = extract_symbol_files_from_archive(
            archive_path=archive_path,
            trade_date_raw=trade_date,
            symbols=symbols,
            stage_root=stage_root,
        )
        try:
            report = backfill_day_package(
                day_dir,
                symbols=symbols,
                large_threshold=large_threshold,
                super_threshold=super_threshold,
                mode=f"repair_{compact}",
                dry_run=False,
            )
            reports.append(
                {
                    "trade_date": trade_date,
                    "symbol_count": len(symbols),
                    "report": report,
                }
            )
        finally:
            if cleanup and day_dir.exists():
                shutil.rmtree(day_dir)

    return {
        "failure_like": failure_like,
        "trade_dates": sorted(grouped.keys()),
        "days": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="定向修复盘后 L2 日级回补失败样本")
    parser.add_argument("--month-root", required=True, help=r"原始包根目录，如 D:\MarketData")
    parser.add_argument("--db-path", default="", help="正式库路径")
    parser.add_argument("--stage-root", required=True, help=r"临时解压目录，如 Z:\l2_repair_stage")
    parser.add_argument("--failure-like", default="OrderID 无法%", help="失败信息 LIKE 条件")
    parser.add_argument("--trade-dates", default="", help="逗号分隔 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    db_path = _get_db_path(args.db_path)
    os.environ["DB_PATH"] = db_path

    trade_dates = []
    for item in args.trade_dates.split(","):
        text = item.strip()
        if not text:
            continue
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        trade_dates.append(text)

    report = repair_failed_samples(
        month_root=Path(args.month_root),
        db_path=db_path,
        stage_root=Path(args.stage_root),
        failure_like=args.failure_like,
        trade_dates=trade_dates or None,
        cleanup=not bool(args.no_cleanup),
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
    )

    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-repair-failed-samples] days={len(report['days'])} "
            f"failure_like={report['failure_like']}"
        )
        for item in report["days"]:
            day_report = item["report"]
            print(
                f"  - trade_date={item['trade_date']} symbols={item['symbol_count']} "
                f"success={day_report['success_symbols']} failed={day_report['failed_symbols']} "
                f"empty={day_report.get('empty_symbols', 0)}"
            )


if __name__ == "__main__":
    main()
