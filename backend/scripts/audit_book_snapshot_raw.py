#!/usr/bin/env python3
"""
审计 L2 日包里的盘口快照 raw 是否足够支撑 book state 层。

目标：
1. 检查 行情.csv 是否具备十档盘口字段与总量字段；
2. 检查连续竞价阶段盘口字段是否稳定非零；
3. 检查 15:00 附近是否存在可作为收盘 bucket 的快照；
4. 为 atomic_book_state_* 的批量回补提供原始证据。
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

BID_PRICE_COLS = [f"申买价{i}" for i in range(1, 11)]
ASK_PRICE_COLS = [f"申卖价{i}" for i in range(1, 11)]
BID_VOL_COLS = [f"申买量{i}" for i in range(1, 11)]
ASK_VOL_COLS = [f"申卖量{i}" for i in range(1, 11)]
TOTAL_COLS = ["叫买总量", "叫卖总量"]


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
    if input_path.is_dir() and (input_path / "行情.csv").is_file():
        return input_path.parent, input_path.parent.name, [input_path]
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date, []


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _audit_symbol(symbol_dir: Path) -> Dict[str, object]:
    quote_path = symbol_dir / "行情.csv"
    if not quote_path.is_file():
        return {"symbol": normalize_symbol_dir_name(symbol_dir.name), "exists": False, "error": "missing 行情.csv"}

    quote = _read_csv(quote_path)
    if "时间" not in quote.columns:
        return {"symbol": normalize_symbol_dir_name(symbol_dir.name), "exists": False, "error": "missing 时间 col"}

    required = BID_PRICE_COLS + ASK_PRICE_COLS + BID_VOL_COLS + ASK_VOL_COLS
    missing = [c for c in required if c not in quote.columns]
    has_total_cols = {c: (c in quote.columns) for c in TOTAL_COLS}

    q = pd.DataFrame({"time": _format_time(quote["时间"])})
    for col in required:
        q[col] = _safe_num(quote[col]) if col in quote.columns else pd.NA
    for col in TOTAL_COLS:
        q[col] = _safe_num(quote[col]) if col in quote.columns else pd.NA

    continuous = q[((q["time"] >= "09:30:00") & (q["time"] <= "11:30:00")) | ((q["time"] >= "13:00:00") & (q["time"] <= "15:00:05"))].copy()
    close_snap = q[(q["time"] >= "14:55:00") & (q["time"] <= "15:00:05")].copy()
    preopen = q[(q["time"] >= "09:15:00") & (q["time"] < "09:30:00")].copy()

    nonzero_bid1 = int((_safe_num(continuous["申买量1"]).fillna(0) > 0).sum()) if "申买量1" in continuous.columns else 0
    nonzero_ask1 = int((_safe_num(continuous["申卖量1"]).fillna(0) > 0).sum()) if "申卖量1" in continuous.columns else 0
    nonzero_top5_bid = int((continuous[[c for c in BID_VOL_COLS if c in continuous.columns]].fillna(0).sum(axis=1) > 0).sum()) if not continuous.empty else 0
    nonzero_top5_ask = int((continuous[[c for c in ASK_VOL_COLS if c in continuous.columns]].fillna(0).sum(axis=1) > 0).sum()) if not continuous.empty else 0
    total_bid_nonzero = int((_safe_num(continuous["叫买总量"]).fillna(0) > 0).sum()) if "叫买总量" in continuous.columns else 0
    total_ask_nonzero = int((_safe_num(continuous["叫卖总量"]).fillna(0) > 0).sum()) if "叫卖总量" in continuous.columns else 0

    return {
        "symbol": normalize_symbol_dir_name(symbol_dir.name),
        "exists": True,
        "rows": int(len(quote)),
        "time_range": [str(q["time"].min()) if not q.empty else None, str(q["time"].max()) if not q.empty else None],
        "missing_required_cols": missing,
        "has_total_cols": has_total_cols,
        "preopen_rows": int(len(preopen)),
        "continuous_rows": int(len(continuous)),
        "close_snapshot_rows": int(len(close_snap)),
        "continuous_nonzero_bid1_rows": nonzero_bid1,
        "continuous_nonzero_ask1_rows": nonzero_ask1,
        "continuous_nonzero_top5_bid_rows": nonzero_top5_bid,
        "continuous_nonzero_top5_ask_rows": nonzero_top5_ask,
        "continuous_nonzero_total_bid_rows": total_bid_nonzero,
        "continuous_nonzero_total_ask_rows": total_ask_nonzero,
        "close_last_time": str(close_snap["time"].max()) if not close_snap.empty else None,
        "raw_support_label": _support_label(missing, len(close_snap), nonzero_top5_bid, nonzero_top5_ask),
    }


def _support_label(missing: Sequence[str], close_rows: int, nonzero_top5_bid: int, nonzero_top5_ask: int) -> str:
    if missing:
        return "insufficient_missing_cols"
    if close_rows <= 0:
        return "insufficient_no_close_snapshot"
    if nonzero_top5_bid <= 0 and nonzero_top5_ask <= 0:
        return "insufficient_zero_depth"
    return "sufficient_for_book_state_basic"


def audit_day_root(input_path: Path, symbols: Optional[Sequence[str]] = None, limit: int = 20) -> Dict[str, object]:
    day_root, trade_date, preselected = _resolve_day_root(input_path)
    symbol_dirs = preselected or list_symbol_dirs(day_root, symbols=symbols)
    if limit > 0:
        symbol_dirs = symbol_dirs[:limit]

    reports: List[Dict[str, object]] = []
    failures: List[Dict[str, str]] = []
    support_counter: Counter = Counter()
    for symbol_dir in symbol_dirs:
        try:
            item = _audit_symbol(symbol_dir)
            reports.append(item)
            support_counter.update([str(item.get("raw_support_label"))])
        except Exception as exc:
            failures.append({"symbol": normalize_symbol_dir_name(symbol_dir.name), "error": str(exc)})
    return {
        "input_path": str(input_path),
        "resolved_day_root": str(day_root),
        "trade_date": trade_date,
        "sampled_symbol_count": len(symbol_dirs),
        "success_count": len(reports),
        "failure_count": len(failures),
        "support_distribution": {str(k): int(v) for k, v in support_counter.most_common()},
        "symbols": reports,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="审计盘口快照 raw 是否足够支撑 book state")
    parser.add_argument("input_path", help="日包目录或 symbol 目录")
    parser.add_argument("--symbols", default="", help="逗号分隔 symbol，如 sh603629,sz000833")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    report = audit_day_root(Path(args.input_path), symbols=symbols or None, limit=int(args.limit))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(
        f"[book-raw-audit] trade_date={report.get('trade_date')} sampled={report['sampled_symbol_count']} "
        f"success={report['success_count']} failure={report['failure_count']} "
        f"support={report['support_distribution']}"
    )
    for item in report["symbols"][:10]:
        print(
            f"  - {item['symbol']} support={item['raw_support_label']} close_rows={item.get('close_snapshot_rows')} "
            f"top5_bid_nonzero={item.get('continuous_nonzero_top5_bid_rows')} top5_ask_nonzero={item.get('continuous_nonzero_top5_ask_rows')}"
        )


if __name__ == "__main__":
    main()
