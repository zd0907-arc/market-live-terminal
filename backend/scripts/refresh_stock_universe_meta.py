"""
刷新正式复盘股票元数据表 stock_universe_meta。

来源固定：ak.stock_zh_a_spot_em()
用途：为 /api/review/pool 提供 name / market_cap / as_of_date。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.db.l2_history_db import replace_stock_universe_meta


def _pick_col(columns: Sequence[str], keywords: Sequence[str]) -> str:
    for col in columns:
        text = str(col)
        if any(keyword in text for keyword in keywords):
            return text
    raise ValueError(f"未找到列: {keywords}")


def _normalize_code6(raw_code: object) -> str:
    text = str(raw_code or "").strip().lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _normalize_symbol(code6: str) -> str:
    if not code6:
        return ""
    if code6.startswith(("60", "68")):
        return f"sh{code6}"
    if code6.startswith(("00", "30")):
        return f"sz{code6}"
    if code6.startswith(("4", "8", "9")):
        return f"bj{code6}"
    return ""


def fetch_stock_universe_rows() -> Tuple[str, List[Tuple[str, str, float]], str]:
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("ak.stock_zh_a_spot_em 返回空表")

    cols = [str(c) for c in df.columns]
    code_col = _pick_col(cols, ["代码"])
    name_col = _pick_col(cols, ["名称"])
    cap_col = _pick_col(cols, ["总市值", "市值"])

    codes = df[code_col].map(_normalize_code6)
    names = df[name_col].astype(str).str.strip()
    caps = pd.to_numeric(df[cap_col], errors="coerce")

    rows: List[Tuple[str, str, float]] = []
    for code6, name, cap in zip(codes, names, caps):
        symbol = _normalize_symbol(code6)
        if not symbol:
            continue
        if pd.isna(cap):
            cap = 0.0
        rows.append((symbol, str(name), float(cap)))

    deduped = list({symbol: (symbol, name, market_cap) for symbol, name, market_cap in rows}.values())
    deduped.sort(key=lambda item: (item[2], item[0]), reverse=True)
    as_of_date = datetime.now().strftime("%Y-%m-%d")
    return as_of_date, deduped, "akshare.stock_zh_a_spot_em"


def refresh_stock_universe_meta() -> dict:
    as_of_date, rows, source = fetch_stock_universe_rows()
    inserted = replace_stock_universe_meta(rows, as_of_date=as_of_date, source=source)
    return {
        "as_of_date": as_of_date,
        "source": source,
        "rows": inserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新正式复盘股票元数据表 stock_universe_meta")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = refresh_stock_universe_meta()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(
        f"[stock-universe-meta] as_of_date={report['as_of_date']} "
        f"rows={report['rows']} source={report['source']}"
    )


if __name__ == "__main__":
    main()
