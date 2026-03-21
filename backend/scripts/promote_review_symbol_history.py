"""
单股票历史补入正式复盘库。

支持两条路径：
1. promote_existing：若 sandbox V2 已有 symbols/{symbol}.db，直接把指定日期区间 promote 到正式库；
2. rebuild_from_raw：若 sandbox V2 不存在，则调用 sandbox_review_etl 对指定 symbol/date 重新跑临时结果，再 promote 到正式库。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.db.l2_history_db import replace_history_5m_l2_rows, replace_history_daily_l2_row
from backend.scripts.promote_sandbox_review_v2_month import _source_root


REVIEW_5M_SELECT_SQL = """
SELECT
    symbol, datetime, source_date,
    open, high, low, close, total_amount,
    l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
    l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell
FROM review_5m_bars
WHERE source_date >= ? AND source_date <= ?
ORDER BY source_date ASC, datetime ASC
"""

History5mInsertRow = Tuple[
    str,
    str,
    str,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    Optional[str],
]


def normalize_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().lower()
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("6", "5")):
            return f"sh{raw}"
        if raw.startswith(("0", "3")):
            return f"sz{raw}"
        if raw.startswith(("4", "8", "9")):
            return f"bj{raw}"
    return raw


def _validate_date(date_text: str) -> None:
    datetime.strptime(date_text, "%Y-%m-%d")


def _read_review_rows(db_path: Path, start_date: str, end_date: str) -> List[History5mInsertRow]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(REVIEW_5M_SELECT_SQL, (start_date, end_date)).fetchall()
    finally:
        conn.close()

    return [
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            float(row[3] or 0.0),
            float(row[4] or 0.0),
            float(row[5] or 0.0),
            float(row[6] or 0.0),
            float(row[7] or 0.0),
            float(row[8] or 0.0),
            float(row[9] or 0.0),
            float(row[10] or 0.0),
            float(row[11] or 0.0),
            float(row[12] or 0.0),
            float(row[13] or 0.0),
            float(row[14] or 0.0),
            float(row[15] or 0.0),
            None,
        )
        for row in rows
    ]


def _compute_daily_row(symbol: str, trade_date: str, rows_5m: Sequence[History5mInsertRow]) -> Optional[Tuple]:
    if not rows_5m:
        return None

    opens = rows_5m[0][3]
    highs = max(row[4] for row in rows_5m)
    lows = min(row[5] for row in rows_5m)
    closes = rows_5m[-1][6]
    total_amount = sum(row[7] for row in rows_5m)
    l1_main_buy = sum(row[8] for row in rows_5m)
    l1_main_sell = sum(row[9] for row in rows_5m)
    l1_super_buy = sum(row[10] for row in rows_5m)
    l1_super_sell = sum(row[11] for row in rows_5m)
    l2_main_buy = sum(row[12] for row in rows_5m)
    l2_main_sell = sum(row[13] for row in rows_5m)
    l2_super_buy = sum(row[14] for row in rows_5m)
    l2_super_sell = sum(row[15] for row in rows_5m)
    quality_messages = [str(row[16]).strip() for row in rows_5m if len(row) > 16 and str(row[16]).strip()]
    quality_info = "；".join(dict.fromkeys(quality_messages)) if quality_messages else None

    def ratio(v: float) -> float:
        return float(v / total_amount * 100) if total_amount > 0 else 0.0

    return (
        symbol,
        trade_date,
        float(opens),
        float(highs),
        float(lows),
        float(closes),
        float(total_amount),
        float(l1_main_buy),
        float(l1_main_sell),
        float(l1_main_buy - l1_main_sell),
        float(l1_super_buy),
        float(l1_super_sell),
        float(l1_super_buy - l1_super_sell),
        float(l2_main_buy),
        float(l2_main_sell),
        float(l2_main_buy - l2_main_sell),
        float(l2_super_buy),
        float(l2_super_sell),
        float(l2_super_buy - l2_super_sell),
        ratio(l1_main_buy + l1_main_sell),
        ratio(l1_super_buy + l1_super_sell),
        ratio(l2_main_buy + l2_main_sell),
        ratio(l2_super_buy + l2_super_sell),
        ratio(l1_main_buy),
        ratio(l1_main_sell),
        ratio(l2_main_buy),
        ratio(l2_main_sell),
        quality_info,
    )


def _promote_rows(symbol: str, rows: Sequence[History5mInsertRow]) -> Dict[str, object]:
    grouped: Dict[str, List[History5mInsertRow]] = defaultdict(list)
    for row in rows:
        grouped[str(row[2])].append(row)

    written_trade_dates: List[str] = []
    rows_5m_total = 0
    rows_daily_total = 0
    for trade_date, day_rows in sorted(grouped.items()):
        rows_5m_total += replace_history_5m_l2_rows(symbol, trade_date, day_rows)
        daily_row = _compute_daily_row(symbol, trade_date, day_rows)
        rows_daily_total += replace_history_daily_l2_row(symbol, trade_date, daily_row)
        written_trade_dates.append(trade_date)

    return {
        "trade_dates": written_trade_dates,
        "trade_day_count": len(written_trade_dates),
        "rows_5m": rows_5m_total,
        "rows_daily": rows_daily_total,
    }


def _existing_symbol_db(source_root: Path, symbol: str) -> Path:
    return source_root / "symbols" / f"{symbol}.db"


def promote_existing_symbol_history(
    symbol: str,
    start_date: str,
    end_date: str,
    source_root: Path,
) -> Dict[str, object]:
    symbol_db = _existing_symbol_db(source_root, symbol)
    if not symbol_db.is_file():
        raise FileNotFoundError(f"sandbox V2 symbol DB 不存在: {symbol_db}")
    rows = _read_review_rows(symbol_db, start_date, end_date)
    if not rows:
        return {
            "mode": "promote_existing",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "source_db": str(symbol_db),
            "trade_dates": [],
            "trade_day_count": 0,
            "rows_5m": 0,
            "rows_daily": 0,
        }
    report = _promote_rows(symbol, rows)
    report.update(
        {
            "mode": "promote_existing",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "source_db": str(symbol_db),
        }
    )
    return report


def rebuild_symbol_history_from_raw(
    symbol: str,
    start_date: str,
    end_date: str,
    raw_src_root: str,
) -> Dict[str, object]:
    raw_root = os.path.abspath(os.path.expanduser(raw_src_root))
    if not os.path.exists(raw_root):
        raise FileNotFoundError(f"原始历史源目录不存在: {raw_root}")

    with tempfile.TemporaryDirectory(prefix=f"review_symbol_{symbol}_") as tmp_dir:
        temp_db = os.path.join(tmp_dir, f"{symbol}.db")
        cmd = [
            sys.executable,
            "-m",
            "backend.scripts.sandbox_review_etl",
            raw_root,
            "--output-db",
            temp_db,
            "--symbol",
            symbol,
            "--start-date",
            start_date,
            "--end-date",
            end_date,
            "--mode",
            "full",
        ]
        proc = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"sandbox_review_etl 失败（exit_code={proc.returncode}）: {proc.stdout}")

        rows = _read_review_rows(Path(temp_db), start_date, end_date)
        if not rows:
            return {
                "mode": "rebuild_from_raw",
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "raw_src_root": raw_root,
                "trade_dates": [],
                "trade_day_count": 0,
                "rows_5m": 0,
                "rows_daily": 0,
                "etl_output": proc.stdout,
            }
        report = _promote_rows(symbol, rows)
        report.update(
            {
                "mode": "rebuild_from_raw",
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "raw_src_root": raw_root,
                "etl_output": proc.stdout,
            }
        )
        return report


def backfill_review_symbol_history(
    symbol: str,
    start_date: str,
    end_date: str,
    mode: str = "auto",
    source_root: Optional[Path] = None,
    raw_src_root: str = "",
) -> Dict[str, object]:
    normalized_symbol = normalize_symbol(symbol)
    if not normalized_symbol.startswith(("sh", "sz", "bj")):
        raise ValueError("symbol 格式错误")
    _validate_date(start_date)
    _validate_date(end_date)
    if end_date < start_date:
        raise ValueError("结束日期必须大于等于开始日期")
    if mode not in {"auto", "promote_existing", "rebuild_from_raw"}:
        raise ValueError("mode 仅支持 auto/promote_existing/rebuild_from_raw")

    resolved_source_root = source_root or Path(
        os.path.abspath(os.getenv("SANDBOX_REVIEW_V2_ROOT", str(_source_root(""))))
    )
    symbol_db = _existing_symbol_db(resolved_source_root, normalized_symbol)
    actual_mode = mode
    if mode == "auto":
        actual_mode = "promote_existing" if symbol_db.is_file() else "rebuild_from_raw"

    if actual_mode == "promote_existing":
        report = promote_existing_symbol_history(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            source_root=resolved_source_root,
        )
    else:
        resolved_raw_src_root = raw_src_root or os.getenv("REVIEW_HISTORY_RAW_SRC_ROOT") or os.getenv("SANDBOX_REVIEW_SRC_ROOT") or r"D:\MarketData"
        report = rebuild_symbol_history_from_raw(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            raw_src_root=resolved_raw_src_root,
        )

    report["requested_mode"] = mode
    report["actual_mode"] = actual_mode
    report["sandbox_source_root"] = str(resolved_source_root)
    report["symbol_db_exists"] = symbol_db.is_file()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="单股票历史补入正式复盘库")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--mode", default="auto", choices=["auto", "promote_existing", "rebuild_from_raw"])
    parser.add_argument("--source-root", default="", help="sandbox review v2 根目录")
    parser.add_argument("--raw-src-root", default="", help="原始历史 CSV/ZIP 根目录，仅 slow path 需要")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = backfill_review_symbol_history(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        mode=args.mode,
        source_root=_source_root(args.source_root),
        raw_src_root=args.raw_src_root,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(
        f"[review-backfill] symbol={report['symbol']} actual_mode={report['actual_mode']} "
        f"trade_days={report['trade_day_count']} rows_5m={report['rows_5m']} rows_daily={report['rows_daily']}"
    )
    if report.get("trade_dates"):
        print(f"[review-backfill] trade_dates={','.join(report['trade_dates'])}")


if __name__ == "__main__":
    main()
