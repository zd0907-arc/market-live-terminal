#!/usr/bin/env python3
"""
审计 L2 日包里集合竞价窗口（09:15~09:25）是否有原始数据，以及覆盖到哪一层。

目标：
1. 判断 trade/order/quote 三类文件是否包含 09:15~09:25 的数据；
2. 判断 09:25 是否能被单独识别，而不是只能看到 09:30 之后；
3. 为“集合竞价如何落库”提供证据，不在设计未定前拍脑袋并桶。

示例：
python3 backend/scripts/audit_l2_auction_window.py D:\\MarketData\\202603\\20260311 --symbols sh603629 --json
python3 backend/scripts/audit_l2_auction_window.py /tmp/day_root --limit 50
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import is_symbol_dir, normalize_month_day_root
from backend.scripts.l2_daily_backfill import list_symbol_dirs, normalize_symbol_dir_name

WINDOWS = {
    "open_auction": ("09:15:00", "09:25:00"),
    "auction_buffer": ("09:25:00", "09:30:00"),
    "continuous_am": ("09:30:00", "11:30:00"),
    "continuous_pm": ("13:00:00", "15:00:00"),
}


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="gb18030", low_memory=False)
    bad_cols = [c for c in df.columns if str(c).strip() == "" or str(c).startswith("Unnamed")]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _format_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ":" + hhmmss.str[2:4] + ":" + hhmmss.str[4:6]


def _resolve_day_root(input_path: Path) -> Tuple[Path, Optional[str], List[Path]]:
    if is_symbol_dir(input_path):
        return input_path.parent, input_path.parent.name, [input_path]
    if input_path.is_dir() and (input_path / "逐笔成交.csv").is_file():
        return input_path.parent, input_path.parent.name, [input_path]
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date, []


def _window_stats(times: pd.Series) -> Dict[str, Dict[str, object]]:
    clean = times.dropna().astype(str)
    result: Dict[str, Dict[str, object]] = {}
    for label, (start, end) in WINDOWS.items():
        if label == "open_auction":
            mask = (clean >= start) & (clean < end)
        else:
            mask = (clean >= start) & (clean < end)
        sliced = clean[mask]
        result[label] = {
            "count": int(len(sliced)),
            "first_time": str(sliced.min()) if not sliced.empty else None,
            "last_time": str(sliced.max()) if not sliced.empty else None,
        }
    return result


def _summarize_times(df: pd.DataFrame, time_col: str) -> Dict[str, object]:
    if time_col not in df.columns:
        return {
            "exists": False,
            "error": f"missing column: {time_col}",
        }
    times = _format_time(df[time_col])
    non_empty = times.dropna()
    exact_0925 = int((non_empty == "09:25:00").sum())
    pre_0930 = int(((non_empty >= "09:15:00") & (non_empty < "09:30:00")).sum())
    return {
        "exists": True,
        "rows": int(len(df)),
        "time_range": [str(non_empty.min()) if not non_empty.empty else None, str(non_empty.max()) if not non_empty.empty else None],
        "pre_0930_rows": pre_0930,
        "exact_0925_rows": exact_0925,
        "windows": _window_stats(non_empty),
    }


def _detect_auction_shape(trade_stats: Dict[str, object], order_stats: Dict[str, object], quote_stats: Dict[str, object]) -> str:
    trade_pre = int(trade_stats.get("pre_0930_rows", 0) or 0) if trade_stats.get("exists") else 0
    order_pre = int(order_stats.get("pre_0930_rows", 0) or 0) if order_stats.get("exists") else 0
    quote_pre = int(quote_stats.get("pre_0930_rows", 0) or 0) if quote_stats.get("exists") else 0
    if trade_pre > 0 and order_pre > 0 and quote_pre > 0:
        return "trade+order+quote"
    if order_pre > 0 and quote_pre > 0 and trade_pre <= 0:
        return "order+quote_only"
    if quote_pre > 0 and trade_pre <= 0 and order_pre <= 0:
        return "quote_only"
    if trade_pre > 0 and order_pre <= 0 and quote_pre <= 0:
        return "trade_only"
    if trade_pre > 0 or order_pre > 0 or quote_pre > 0:
        return "partial_mixed"
    return "no_pre_0930_data"


def _audit_symbol(symbol_dir: Path) -> Dict[str, object]:
    trade_path = symbol_dir / "逐笔成交.csv"
    order_path = symbol_dir / "逐笔委托.csv"
    quote_path = symbol_dir / "行情.csv"

    trade_stats: Dict[str, object]
    order_stats: Dict[str, object]
    quote_stats: Dict[str, object]

    try:
        trade_stats = _summarize_times(_read_csv(trade_path), "时间") if trade_path.is_file() else {"exists": False, "error": "missing file"}
    except Exception as exc:
        trade_stats = {"exists": False, "error": str(exc)}

    try:
        order_stats = _summarize_times(_read_csv(order_path), "时间") if order_path.is_file() else {"exists": False, "error": "missing file"}
    except Exception as exc:
        order_stats = {"exists": False, "error": str(exc)}

    try:
        quote_stats = _summarize_times(_read_csv(quote_path), "时间") if quote_path.is_file() else {"exists": False, "error": "missing file"}
    except Exception as exc:
        quote_stats = {"exists": False, "error": str(exc)}

    return {
        "symbol": normalize_symbol_dir_name(symbol_dir.name),
        "raw_symbol_dir": symbol_dir.name,
        "auction_shape": _detect_auction_shape(trade_stats, order_stats, quote_stats),
        "trade": trade_stats,
        "order": order_stats,
        "quote": quote_stats,
    }


def audit_day_root(input_path: Path, symbols: Optional[Sequence[str]] = None, limit: int = 20) -> Dict[str, object]:
    day_root, trade_date, preselected = _resolve_day_root(input_path)
    symbol_dirs = preselected or list_symbol_dirs(day_root, symbols=symbols)
    if limit > 0:
        symbol_dirs = symbol_dirs[:limit]

    reports: List[Dict[str, object]] = []
    failures: List[Dict[str, str]] = []
    shape_counter: Counter = Counter()

    for symbol_dir in symbol_dirs:
        try:
            report = _audit_symbol(symbol_dir)
            reports.append(report)
            shape_counter.update([report["auction_shape"]])
        except Exception as exc:
            failures.append({
                "symbol": normalize_symbol_dir_name(symbol_dir.name),
                "error": str(exc),
            })

    return {
        "input_path": str(input_path),
        "resolved_day_root": str(day_root),
        "trade_date": trade_date,
        "sampled_symbol_count": len(symbol_dirs),
        "success_count": len(reports),
        "failure_count": len(failures),
        "auction_shape_distribution": {str(k): int(v) for k, v in shape_counter.most_common()},
        "symbols": reports,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="审计 L2 日包集合竞价窗口覆盖情况")
    parser.add_argument("input_path", help="日包目录或 symbol 目录")
    parser.add_argument("--symbols", default="", help="逗号分隔 symbol，如 sh603629,sz000833")
    parser.add_argument("--limit", type=int, default=20, help="最多审计多少只股票，0=不限制")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    report = audit_day_root(Path(args.input_path), symbols=symbols or None, limit=int(args.limit))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(
        f"[auction-audit] trade_date={report.get('trade_date')} sampled={report['sampled_symbol_count']} "
        f"success={report['success_count']} failure={report['failure_count']} "
        f"shapes={report['auction_shape_distribution']}"
    )
    for item in report["symbols"][:10]:
        trade_pre = item.get("trade", {}).get("pre_0930_rows")
        order_pre = item.get("order", {}).get("pre_0930_rows")
        quote_pre = item.get("quote", {}).get("pre_0930_rows")
        print(
            f"  - {item['symbol']} shape={item['auction_shape']} trade_pre={trade_pre} order_pre={order_pre} quote_pre={quote_pre}"
        )


if __name__ == "__main__":
    main()
