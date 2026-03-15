"""
定位盘后 L2 正式表中缺失的 symbol-day，并分析其为何未形成正式 5m + daily。

用途：
- 重建“空结果样本”清单；
- 区分停牌/无成交/仅集合竞价/源文件异常等模式；
- 为后续 repair queue 提供可执行分类。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_daily_backfill import (
    REQUIRED_FILES,
    _format_trade_time,
    _read_csv,
    canonical_trade_date,
    list_symbol_dirs,
    normalize_symbol_dir_name,
    process_symbol_dir,
)


ARCHIVE_SYMBOL_RE = re.compile(r"^(?P<day>\d{8})/(?P<vendor>[0-9]{6}\.(?:SZ|SH|BJ))/$", re.I)


def _get_db_path(explicit_db_path: str = "") -> str:
    return explicit_db_path or os.getenv("DB_PATH") or os.path.join(ROOT_DIR, "data", "market_data.db")


def _list_archive_symbols(archive_path: Path) -> List[str]:
    result = subprocess.run(["tar", "-tf", str(archive_path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"读取 archive 失败: {archive_path} :: {result.stderr.strip()}")
    symbols: List[str] = []
    for line in result.stdout.splitlines():
        match = ARCHIVE_SYMBOL_RE.match(line.strip())
        if not match:
            continue
        vendor_dir = match.group("vendor").lower()
        code, market = vendor_dir.split(".")
        symbols.append(f"{market}{code}")
    return sorted(set(symbols))


def _query_existing_daily_symbols(db_path: str, trade_date: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT symbol FROM history_daily_l2 WHERE date=? ORDER BY symbol",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _symbol_to_vendor_dir(symbol: str) -> str:
    text = (symbol or "").strip().lower()
    market = text[:2].upper()
    code = text[2:]
    return f"{code}.{market}"


def _extract_symbols(
    archive_path: Path,
    trade_date: str,
    symbols: Sequence[str],
    stage_root: Path,
    files: Sequence[str] = REQUIRED_FILES,
) -> Path:
    compact = trade_date.replace("-", "")
    day_dir = stage_root / compact
    if day_dir.exists():
        shutil.rmtree(day_dir)
    stage_root.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        vendor = _symbol_to_vendor_dir(symbol)
        members = [f"{compact}/{vendor}/{name}" for name in files]
        result = subprocess.run(
            ["tar", "-xf", str(archive_path), "-C", str(stage_root), *members],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"抽取失败: {archive_path} :: {result.stderr.strip()}")
    return day_dir


def _safe_trade_profile(symbol_dir: Path) -> Dict[str, object]:
    trade_path = symbol_dir / "逐笔成交.csv"
    profile: Dict[str, object] = {
        "trade_rows_raw": 0,
        "continuous_rows": 0,
        "auction_rows": 0,
        "outside_rows": 0,
        "raw_time_min": None,
        "raw_time_max": None,
        "bs_counts": {},
    }
    if not trade_path.is_file():
        profile["profile_error"] = "missing_trade_file"
        return profile

    trade = _read_csv(trade_path)
    profile["trade_rows_raw"] = int(len(trade))
    if trade.empty or "时间" not in trade.columns:
        return profile

    times = _format_trade_time(trade["时间"])
    profile["raw_time_min"] = times.min() if len(times) else None
    profile["raw_time_max"] = times.max() if len(times) else None

    continuous_mask = (
        ((times >= "09:30:00") & (times <= "11:30:00"))
        | ((times >= "13:00:00") & (times <= "15:00:00"))
    )
    auction_mask = (
        ((times >= "09:15:00") & (times < "09:30:00"))
        | ((times > "15:00:00") & (times <= "15:30:00"))
    )
    profile["continuous_rows"] = int(continuous_mask.sum())
    profile["auction_rows"] = int((auction_mask & ~continuous_mask).sum())
    profile["outside_rows"] = int((~continuous_mask & ~auction_mask).sum())
    if "BS标志" in trade.columns:
        profile["bs_counts"] = (
            trade["BS标志"].astype(str).str.strip().str.upper().value_counts().to_dict()
        )
    return profile


def _classify_empty_sample(diagnostics: Dict[str, object], trade_profile: Dict[str, object]) -> str:
    trade_rows_raw = int(trade_profile.get("trade_rows_raw", 0) or 0)
    continuous_rows = int(trade_profile.get("continuous_rows", 0) or 0)
    auction_rows = int(trade_profile.get("auction_rows", 0) or 0)
    ticks_rows = int(diagnostics.get("ticks_rows", 0) or 0)
    bars_5m = int(diagnostics.get("bars_5m", 0) or 0)

    if trade_rows_raw == 0:
        return "empty_trade_file"
    if continuous_rows == 0 and auction_rows > 0:
        return "auction_only_no_continuous_trades"
    if continuous_rows == 0:
        return "no_continuous_session_trades"
    if ticks_rows == 0:
        return "continuous_trades_all_filtered_invalid"
    if bars_5m == 0:
        return "ticks_exist_but_no_5m_bar"
    return "other_missing_daily"


def _classify_by_trade_profile_only(trade_profile: Dict[str, object]) -> str:
    trade_rows_raw = int(trade_profile.get("trade_rows_raw", 0) or 0)
    continuous_rows = int(trade_profile.get("continuous_rows", 0) or 0)
    auction_rows = int(trade_profile.get("auction_rows", 0) or 0)
    outside_rows = int(trade_profile.get("outside_rows", 0) or 0)

    if trade_rows_raw == 0:
        return "empty_trade_file"
    if continuous_rows == 0 and auction_rows > 0:
        return "auction_only_no_continuous_trades"
    if continuous_rows == 0 and outside_rows > 0:
        return "outside_session_only_trades"
    if continuous_rows == 0:
        return "no_continuous_session_trades"
    return "has_continuous_rows_need_deep_review"


def review_empty_samples(
    month_root: Path,
    db_path: str,
    stage_root: Path,
    trade_dates: Sequence[str],
) -> Dict[str, object]:
    per_day: List[Dict[str, object]] = []
    category_counter: Counter[str] = Counter()

    for trade_date in trade_dates:
        compact = trade_date.replace("-", "")
        archive_path = Path(month_root) / compact[:6] / f"{compact}.7z"
        archive_symbols = _list_archive_symbols(archive_path)
        existing_symbols = _query_existing_daily_symbols(db_path=db_path, trade_date=trade_date)
        missing_symbols = sorted(set(archive_symbols) - set(existing_symbols))
        if not missing_symbols:
            per_day.append(
                {"trade_date": trade_date, "archive_symbols": len(archive_symbols), "missing_symbols": []}
            )
            continue

        day_dir = _extract_symbols(
            archive_path,
            trade_date,
            missing_symbols,
            stage_root,
            files=("逐笔成交.csv",),
        )
        day_records: List[Dict[str, object]] = []
        try:
            deep_review_symbols: List[str] = []
            for symbol_dir in list_symbol_dirs(day_dir):
                symbol = normalize_symbol_dir_name(symbol_dir.name)
                trade_profile = _safe_trade_profile(symbol_dir)
                classification = _classify_by_trade_profile_only(trade_profile)
                record = {
                    "symbol": symbol,
                    "classification": classification,
                    "trade_profile": trade_profile,
                }
                category_counter[classification] += 1
                day_records.append(record)
                if classification == "has_continuous_rows_need_deep_review":
                    deep_review_symbols.append(symbol)

            if deep_review_symbols:
                shutil.rmtree(day_dir)
                day_dir = _extract_symbols(
                    archive_path,
                    trade_date,
                    deep_review_symbols,
                    stage_root,
                    files=REQUIRED_FILES,
                )
                indexed_records = {item["symbol"]: item for item in day_records}
                for symbol_dir in list_symbol_dirs(day_dir):
                    symbol = normalize_symbol_dir_name(symbol_dir.name)
                    if symbol not in indexed_records:
                        continue
                    trade_profile = indexed_records[symbol]["trade_profile"]
                    category_counter["has_continuous_rows_need_deep_review"] -= 1
                    try:
                        _, rows_5m, daily_row, diagnostics = process_symbol_dir(
                            symbol_dir,
                            canonical_trade_date(compact),
                            200000.0,
                            1000000.0,
                        )
                        diagnostics = dict(diagnostics)
                        diagnostics["bars_5m"] = len(rows_5m)
                        diagnostics["has_daily"] = daily_row is not None
                        classification = _classify_empty_sample(diagnostics, trade_profile)
                        indexed_records[symbol]["classification"] = classification
                        indexed_records[symbol]["diagnostics"] = diagnostics
                        category_counter[classification] += 1
                    except Exception as exc:
                        classification = f"exception:{type(exc).__name__}"
                        indexed_records[symbol]["classification"] = classification
                        indexed_records[symbol]["error"] = str(exc)
                        category_counter[classification] += 1
        finally:
            if day_dir.exists():
                shutil.rmtree(day_dir)

        per_day.append(
            {
                "trade_date": trade_date,
                "archive_symbols": len(archive_symbols),
                "existing_daily_symbols": len(existing_symbols),
                "missing_symbols": day_records,
            }
        )

    return {
        "trade_dates": list(trade_dates),
        "summary": dict(category_counter),
        "days": per_day,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="复核盘后 L2 空结果样本")
    parser.add_argument("--month-root", required=True, help=r"原始包根目录，如 D:\MarketData")
    parser.add_argument("--db-path", default="", help="正式库路径")
    parser.add_argument("--stage-root", required=True, help=r"临时解压目录，如 Z:\l2_empty_review")
    parser.add_argument("--trade-dates", required=True, help="逗号分隔 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--output-json", default="", help="可选输出 json 文件路径")
    args = parser.parse_args()

    db_path = _get_db_path(args.db_path)
    trade_dates: List[str] = []
    for item in args.trade_dates.split(","):
        text = item.strip()
        if not text:
            continue
        if len(text) == 8 and text.isdigit():
            text = canonical_trade_date(text)
        trade_dates.append(text)

    report = review_empty_samples(
        month_root=Path(args.month_root),
        db_path=db_path,
        stage_root=Path(args.stage_root),
        trade_dates=trade_dates,
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
