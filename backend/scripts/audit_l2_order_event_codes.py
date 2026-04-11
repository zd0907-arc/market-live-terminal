"""
审计盘后 L2 日包中的挂单事件码分布。

用途：
1. 判断某个日包/样本股票使用的是哪套事件编码（如 0/1/U 或 A/D/S）；
2. 统计 `委托类型` / `委托代码` 的分布；
3. 为“正式链路该兼容哪些编码体系”提供证据。

示例：
python3 backend/scripts/audit_l2_order_event_codes.py /tmp/lt_l2/20260311 --symbols sh603629 --json
python3 backend/scripts/audit_l2_order_event_codes.py /tmp/day_root --limit 50
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


KNOWN_STYLE_MAP = {
    frozenset({"0", "1", "U"}): "numeric_01u",
    frozenset({"A", "D", "S"}): "alpha_ads",
}


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="gb18030", low_memory=False)
    bad_cols = [c for c in df.columns if str(c).strip() == "" or str(c).startswith("Unnamed")]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _resolve_day_root(input_path: Path) -> Tuple[Path, Optional[str]]:
    if is_symbol_dir(input_path):
        return input_path.parent, input_path.parent.name
    if input_path.is_dir() and (input_path / "逐笔委托.csv").is_file():
        return input_path.parent, input_path.parent.name
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date


def _counter_to_dict(counter: Counter, top_n: int = 12) -> Dict[str, int]:
    return {str(k): int(v) for k, v in counter.most_common(top_n)}


def _detect_style(type_counter: Counter) -> str:
    keys = {str(k) for k in type_counter.keys() if str(k)}
    if not keys:
        return "empty"
    for known_keys, label in KNOWN_STYLE_MAP.items():
        if keys.issubset(known_keys):
            return label
    if {"A", "D"} & keys and {"0", "1", "U"} & keys:
        return "mixed_alpha_numeric"
    return "unknown_or_custom"


def _audit_symbol(symbol_dir: Path) -> Dict[str, object]:
    order_path = symbol_dir / "逐笔委托.csv"
    if not order_path.is_file():
        raise FileNotFoundError(f"缺少逐笔委托.csv: {order_path}")

    df = _read_csv(order_path)
    required = ["委托类型", "委托代码"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"逐笔委托缺列: {', '.join(missing)}")

    type_counter = Counter(df["委托类型"].astype(str).str.strip().str.upper())
    side_counter = Counter(df["委托代码"].astype(str).str.strip().str.upper())
    nonzero_order_id_ratio = None
    if "交易所委托号" in df.columns:
        ids = pd.to_numeric(df["交易所委托号"], errors="coerce").fillna(0)
        nonzero_order_id_ratio = float((ids > 0).mean())

    return {
        "symbol": normalize_symbol_dir_name(symbol_dir.name),
        "raw_symbol_dir": symbol_dir.name,
        "rows": int(len(df)),
        "event_type_top": _counter_to_dict(type_counter),
        "side_top": _counter_to_dict(side_counter),
        "encoding_style": _detect_style(type_counter),
        "nonzero_order_id_ratio": round(nonzero_order_id_ratio, 4) if nonzero_order_id_ratio is not None else None,
    }


def audit_day_root(input_path: Path, symbols: Optional[Sequence[str]] = None, limit: int = 20) -> Dict[str, object]:
    if input_path.is_dir() and (input_path / "逐笔委托.csv").is_file():
        day_root = input_path.parent
        trade_date = input_path.parent.name
        symbol_dirs = [input_path]
    else:
        day_root, trade_date = _resolve_day_root(input_path)
        symbol_dirs = list_symbol_dirs(day_root, symbols=symbols)
    if limit > 0:
        symbol_dirs = symbol_dirs[:limit]

    reports: List[Dict[str, object]] = []
    failures: List[Dict[str, str]] = []
    style_counter: Counter = Counter()
    agg_type_counter: Counter = Counter()
    agg_side_counter: Counter = Counter()

    for symbol_dir in symbol_dirs:
        try:
            report = _audit_symbol(symbol_dir)
            reports.append(report)
            style_counter.update([str(report["encoding_style"])])
            agg_type_counter.update(report["event_type_top"])
            agg_side_counter.update(report["side_top"])
        except Exception as exc:
            failures.append(
                {
                    "symbol": normalize_symbol_dir_name(symbol_dir.name),
                    "error": str(exc),
                }
            )

    return {
        "input_path": str(input_path),
        "resolved_day_root": str(day_root),
        "trade_date": trade_date,
        "sampled_symbol_count": len(symbol_dirs),
        "success_count": len(reports),
        "failure_count": len(failures),
        "style_distribution": _counter_to_dict(style_counter),
        "aggregate_event_type_top": _counter_to_dict(agg_type_counter),
        "aggregate_side_top": _counter_to_dict(agg_side_counter),
        "symbols": reports,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="审计 L2 日包挂单事件码分布")
    parser.add_argument("input_path", help="日包目录或 symbol 目录")
    parser.add_argument("--symbols", default="", help="逗号分隔 symbol，如 sh603629,sz000833")
    parser.add_argument("--limit", type=int, default=20, help="最多审计多少只股票，0=不限制")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    report = audit_day_root(Path(args.input_path), symbols=symbols or None, limit=int(args.limit))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[order-code-audit] trade_date={report.get('trade_date')} "
            f"sampled={report['sampled_symbol_count']} success={report['success_count']} "
            f"failure={report['failure_count']} styles={report['style_distribution']}"
        )
        for item in report["symbols"][:10]:
            print(
                f"  - {item['symbol']} style={item['encoding_style']} "
                f"types={item['event_type_top']} sides={item['side_top']}"
            )


if __name__ == "__main__":
    main()
