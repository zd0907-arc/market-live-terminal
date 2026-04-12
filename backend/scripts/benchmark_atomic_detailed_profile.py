#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import backend.scripts.backfill_atomic_order_from_raw as order_mod
import backend.scripts.build_book_state_from_raw as book_mod
import backend.scripts.build_open_auction_summaries as auction_mod
from backend.scripts.run_atomic_backfill_windows import list_l2_symbol_dirs, normalize_symbol_dir_name
from backend.scripts.run_atomic_backfill_windows import (
    _build_atomic_trade_5m_rows_from_l2,
    _build_atomic_trade_daily_row,
)
from backend.scripts.backfill_atomic_order_from_raw import _build_order_rows, load_l2_symbol_bundle
from backend.scripts.build_book_state_from_raw import build_book_rows
from backend.scripts.build_open_auction_summaries import (
    _build_l1_summary_from_frames,
    _build_l2_summary_from_frames,
    _build_manifest,
    _build_phase_l1_summary_from_frames,
    _build_phase_l2_summary_from_frames,
    _prepare_order_auction_df,
    _prepare_quote_auction_df,
    _prepare_trade_auction_df,
)


class ReadProfiler:
    def __init__(self) -> None:
        self.events: List[Dict[str, object]] = []

    def wrap(self, module_name: str, reader: Callable):
        def _wrapped(path: Path, *args, **kwargs):
            t0 = time.perf_counter()
            df = reader(path, *args, **kwargs)
            elapsed = time.perf_counter() - t0
            try:
                size_mb = round(path.stat().st_size / 1024 / 1024, 3)
            except Exception:
                size_mb = None
            self.events.append(
                {
                    "module": module_name,
                    "file": path.name,
                    "path": str(path),
                    "elapsed_sec": elapsed,
                    "rows": int(len(df)),
                    "size_mb": size_mb,
                }
            )
            return df

        return _wrapped

    def summarize(self) -> Dict[str, object]:
        by_file: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "elapsed_sec": 0.0, "rows": 0})
        for item in self.events:
            bucket = by_file[str(item["file"])]
            bucket["count"] += 1
            bucket["elapsed_sec"] += float(item["elapsed_sec"])
            bucket["rows"] += int(item["rows"])
        return {
            "csv_read_count": len(self.events),
            "csv_read_sec": round(sum(float(item["elapsed_sec"]) for item in self.events), 3),
            "by_file": {
                key: {
                    "count": int(val["count"]),
                    "elapsed_sec": round(val["elapsed_sec"], 3),
                    "rows": int(val["rows"]),
                }
                for key, val in sorted(by_file.items())
            },
            "events": [
                {
                    **item,
                    "elapsed_sec": round(float(item["elapsed_sec"]), 3),
                }
                for item in self.events
            ],
        }


@contextmanager
def patch_csv_readers(profiler: ReadProfiler):
    old_order = order_mod._read_csv
    old_book = book_mod._read_csv
    old_auction = auction_mod._read_csv
    order_mod._read_csv = profiler.wrap("order", old_order)
    book_mod._read_csv = profiler.wrap("book", old_book)
    auction_mod._read_csv = profiler.wrap("auction", old_auction)
    try:
        yield
    finally:
        order_mod._read_csv = old_order
        book_mod._read_csv = old_book
        auction_mod._read_csv = old_auction


def trade_date_from_day_root(day_root: Path) -> str:
    name = day_root.name
    return f"{name[:4]}-{name[4:6]}-{name[6:]}"


def profile_symbol(symbol_dir: Path, trade_date: str, large_threshold: float, super_threshold: float) -> Dict[str, object]:
    profiler = ReadProfiler()
    stage_sec: Dict[str, float] = {}

    with patch_csv_readers(profiler):
        t0 = time.perf_counter()
        prepared = load_l2_symbol_bundle(symbol_dir, trade_date)
        stage_sec["load_bundle"] = time.perf_counter() - t0

        t1 = time.perf_counter()
        trade_rows, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_l2(
            symbol_dir, trade_date, large_threshold, super_threshold, prepared=prepared
        )
        daily_trade = _build_atomic_trade_daily_row(
            normalize_symbol_dir_name(symbol_dir.name),
            trade_date,
            trade_rows,
            "trade_order",
            quality_info,
            daily_feature,
        )
        stage_sec["trade"] = time.perf_counter() - t1

        t2 = time.perf_counter()
        _, order_rows, daily_order, order_diag = _build_order_rows(symbol_dir, trade_date, prepared=prepared)
        stage_sec["order"] = time.perf_counter() - t2

        t3 = time.perf_counter()
        book_rows, daily_book = build_book_rows(symbol_dir, trade_date, quote_df=prepared.quote_raw)
        stage_sec["book"] = time.perf_counter() - t3

        compact = trade_date.replace("-", "")
        auction_trade_df = _prepare_trade_auction_df(prepared.trade_raw)
        auction_order_df = _prepare_order_auction_df(prepared.order_raw)
        auction_quote_df = _prepare_quote_auction_df(prepared.quote_raw)

        t4 = time.perf_counter()
        l1_row = _build_l1_summary_from_frames(prepared.symbol, compact, auction_trade_df, auction_quote_df, prepared.quote_raw)
        stage_sec["auction_l1"] = time.perf_counter() - t4

        t5 = time.perf_counter()
        l2_row = _build_l2_summary_from_frames(prepared.symbol, compact, auction_trade_df, auction_order_df)
        stage_sec["auction_l2"] = time.perf_counter() - t5

        t6 = time.perf_counter()
        phase_l1_row = _build_phase_l1_summary_from_frames(prepared.symbol, compact, auction_trade_df, auction_quote_df)
        stage_sec["auction_phase_l1"] = time.perf_counter() - t6

        t7 = time.perf_counter()
        phase_l2_row = _build_phase_l2_summary_from_frames(prepared.symbol, compact, auction_trade_df, auction_order_df)
        stage_sec["auction_phase_l2"] = time.perf_counter() - t7

        t8 = time.perf_counter()
        manifest = _build_manifest(l1_row, l2_row)
        stage_sec["auction_manifest"] = time.perf_counter() - t8

    total_sec = sum(stage_sec.values())
    return {
        "symbol": normalize_symbol_dir_name(symbol_dir.name),
        "stage_sec": {k: round(v, 3) for k, v in stage_sec.items()},
        "total_stage_sec": round(total_sec, 3),
        "csv_profile": profiler.summarize(),
        "outputs": {
            "trade_5m_rows": len(trade_rows),
            "order_5m_rows": len(order_rows),
            "book_5m_rows": len(book_rows),
            "has_trade_daily": bool(daily_trade),
            "has_order_daily": bool(daily_order),
            "has_book_daily": bool(daily_book),
            "order_diag": order_diag,
            "manifest_available": bool(manifest),
        },
    }


def aggregate_results(results: Sequence[Dict[str, object]]) -> Dict[str, object]:
    if not results:
        return {}
    stage_totals: Dict[str, float] = defaultdict(float)
    csv_file_totals: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "elapsed_sec": 0.0})
    csv_read_count = 0
    csv_read_sec = 0.0
    for item in results:
        for stage, value in item["stage_sec"].items():
            stage_totals[stage] += float(value)
        csv_profile = item["csv_profile"]
        csv_read_count += int(csv_profile["csv_read_count"])
        csv_read_sec += float(csv_profile["csv_read_sec"])
        for file_name, stat in csv_profile["by_file"].items():
            csv_file_totals[file_name]["count"] += int(stat["count"])
            csv_file_totals[file_name]["elapsed_sec"] += float(stat["elapsed_sec"])
    count = len(results)
    stage_avg = {k: round(v / count, 3) for k, v in sorted(stage_totals.items())}
    return {
        "sample_symbols": count,
        "avg_stage_sec": stage_avg,
        "avg_total_stage_sec": round(sum(stage_totals.values()) / count, 3),
        "avg_csv_read_count": round(csv_read_count / count, 2),
        "avg_csv_read_sec": round(csv_read_sec / count, 3),
        "csv_file_avg": {
            file_name: {
                "avg_count": round(stat["count"] / count, 2),
                "avg_elapsed_sec": round(stat["elapsed_sec"] / count, 3),
            }
            for file_name, stat in sorted(csv_file_totals.items())
        },
    }


def estimate_day(aggregate: Dict[str, object], total_symbols: int) -> Dict[str, object]:
    avg_sec = float(aggregate.get("avg_total_stage_sec") or 0.0)
    if avg_sec <= 0 or total_symbols <= 0:
        return {}
    total_sec = avg_sec * total_symbols
    return {
        "total_symbols": total_symbols,
        "avg_sec_per_symbol": round(avg_sec, 3),
        "estimated_symbol_per_min": round(60.0 / avg_sec, 2),
        "estimated_day_hours_single_stream": round(total_sec / 3600.0, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day-root", required=True)
    ap.add_argument("--max-symbols", type=int, default=8)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--large-threshold", type=float, default=200000.0)
    ap.add_argument("--super-threshold", type=float, default=1000000.0)
    ap.add_argument("--exclude-gem", action="store_true")
    ap.add_argument("--main-board-only", action="store_true")
    args = ap.parse_args()

    day_root = Path(args.day_root)
    symbol_filter = [s.strip().lower() for s in str(args.symbols).split(",") if s.strip()]
    items = list_l2_symbol_dirs(
        day_root,
        include_bj=False,
        include_star=False,
        include_gem=not args.exclude_gem,
        main_board_only=args.main_board_only,
    )
    if symbol_filter:
        wanted = set(symbol_filter)
        items = [item for item in items if normalize_symbol_dir_name(item.name) in wanted]
    else:
        items = items[: args.max_symbols]
    trade_date = trade_date_from_day_root(day_root)
    results = [
        profile_symbol(item, trade_date, args.large_threshold, args.super_threshold)
        for item in items
    ]
    aggregate = aggregate_results(results)
    estimate = estimate_day(
        aggregate,
        len(
            list_l2_symbol_dirs(
                day_root,
                include_bj=False,
                include_star=False,
                include_gem=not args.exclude_gem,
                main_board_only=args.main_board_only,
            )
        ),
    )
    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "sample_count": len(results),
                "aggregate": aggregate,
                "estimate": estimate,
                "symbols": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
