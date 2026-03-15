"""
按月顺序解压并执行盘后 L2 正式回补。

适用场景：
- Windows 已下载一批 `YYYYMMDD.7z`
- 需要按“解压 -> 回补 -> （可选）清理解压目录”串行处理

示例：
python backend/scripts/l2_month_backfill.py D:\\MarketData\\202603 --db-path D:\\market-live-terminal\\data\\market_data.db --cleanup-extracted --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_daily_backfill import backfill_day_package


def _discover_ready_days(month_dir: Path) -> List[str]:
    ready_days: List[str] = []
    for child in sorted(month_dir.iterdir()):
      if child.is_file() and child.name.endswith(".7z") and child.stem.isdigit() and len(child.stem) == 8:
        ready_days.append(child.stem)
    return ready_days


def _extract_day_archive(month_dir: Path, day: str) -> Path:
    archive_path = month_dir / f"{day}.7z"
    if not archive_path.is_file():
        raise FileNotFoundError(f"缺少日包: {archive_path}")

    day_dir = month_dir / day
    if day_dir.is_dir():
        return day_dir

    result = subprocess.run(
        ["tar", "-xf", str(archive_path), "-C", str(month_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"解压失败: {archive_path} :: {result.stderr.strip()}")
    if not day_dir.is_dir():
        raise RuntimeError(f"解压后未找到目录: {day_dir}")
    return day_dir


def _cleanup_day_dir(day_dir: Path) -> None:
    if day_dir.is_dir():
        shutil.rmtree(day_dir)


def backfill_month_archives(
    month_dir: Path,
    days: Optional[Sequence[str]] = None,
    symbols: Optional[Sequence[str]] = None,
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
    mode: str = "manual_batch",
    dry_run: bool = False,
    cleanup_extracted: bool = False,
) -> Dict[str, object]:
    month_dir = Path(month_dir)
    if not month_dir.is_dir():
        raise ValueError(f"无效月份目录: {month_dir}")

    target_days = list(days) if days else _discover_ready_days(month_dir)
    if not target_days:
        raise ValueError(f"未发现可处理的 .7z 日包: {month_dir}")

    reports: List[Dict[str, object]] = []
    for day in target_days:
        day_report: Dict[str, object] = {"day": day}
        day_dir = _extract_day_archive(month_dir, day)
        day_report["day_dir"] = str(day_dir)
        try:
            report = backfill_day_package(
                day_dir,
                symbols=symbols,
                large_threshold=large_threshold,
                super_threshold=super_threshold,
                mode=mode,
                dry_run=dry_run,
            )
            day_report["backfill"] = report
        finally:
            if cleanup_extracted:
                _cleanup_day_dir(day_dir)
                day_report["cleaned_up"] = True
        reports.append(day_report)

    return {
        "month_dir": str(month_dir),
        "days": target_days,
        "reports": reports,
        "cleanup_extracted": cleanup_extracted,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按月顺序解压并执行 L2 正式回补")
    parser.add_argument("month_dir", help=r"月份目录，如 D:\MarketData\202603")
    parser.add_argument("--days", default="", help="逗号分隔的 YYYYMMDD；留空自动扫描完整 .7z")
    parser.add_argument("--symbols", default="", help="逗号分隔的 symbol，如 sz000833,sh600519；留空为全目录")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--mode", default="manual_batch")
    parser.add_argument("--db-path", default="", help="可选 DB 路径；默认使用环境变量 DB_PATH 或 data/market_data.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cleanup-extracted", action="store_true", help="回补后删除解压目录，保留原始 .7z")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.db_path:
        os.environ["DB_PATH"] = os.path.abspath(args.db_path)

    days = [item.strip() for item in args.days.split(",") if item.strip()]
    symbols = [item.strip().lower() for item in args.symbols.split(",") if item.strip()]

    report = backfill_month_archives(
        Path(args.month_dir),
        days=days or None,
        symbols=symbols or None,
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
        mode=args.mode,
        dry_run=bool(args.dry_run),
        cleanup_extracted=bool(args.cleanup_extracted),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-month-backfill] month_dir={report['month_dir']} "
            f"days={len(report['days'])} cleanup_extracted={report['cleanup_extracted']} "
            f"dry_run={report['dry_run']}"
        )
        for item in report["reports"]:
            backfill = item.get("backfill", {})
            print(
                f"  - day={item['day']} success={backfill.get('success_symbols')} "
                f"failed={backfill.get('failed_symbols')} rows_5m={backfill.get('rows_5m')} "
                f"rows_daily={backfill.get('rows_daily')}"
            )


if __name__ == "__main__":
    main()
