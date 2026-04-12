#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.run_atomic_backfill_windows import _run_process_shard, list_l2_symbol_dirs


def trade_date_from_day_root(day_root: Path) -> str:
    name = day_root.name
    return f"{name[:4]}-{name[4:6]}-{name[6:]}"


def _run_shard(day_root: str, symbol_dirs: Sequence[str], out_db: str, max_error_details: int = 5) -> Dict[str, object]:
    result = _run_process_shard(
        "l2",
        trade_date_from_day_root(Path(day_root)),
        out_db,
        symbol_dirs,
        200000.0,
        1000000.0,
    )
    return {
        "ok": int(result.get("success_count", 0)),
        "fail": int(result.get("failure_count", 0)),
        "errors": list(result.get("failures", []))[:max_error_details],
    }


def bench_process_shards(day_root: Path, items: Sequence[Path], workers: int, out_dir: Path) -> Dict[str, object]:
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    shards = [list(items[i::workers]) for i in range(workers)]
    started = time.perf_counter()
    ok = 0
    fail = 0
    dbs: List[Path] = []
    error_details: List[Dict[str, str]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        future_map = {}
        for idx, shard in enumerate(shards, start=1):
            if not shard:
                continue
            db = out_dir / f"proc_{idx}.db"
            dbs.append(db)
            future_map[
                ex.submit(
                    _run_shard,
                    str(day_root),
                    [str(x) for x in shard],
                    str(db),
                    5,
                )
            ] = idx
        for future in as_completed(future_map):
            result = future.result()
            ok += int(result["ok"])
            fail += int(result["fail"])
            error_details.extend(result.get("errors", []))
    elapsed = time.perf_counter() - started

    total_size = 0
    total_trade_daily = 0
    total_trade_5m = 0
    for db in dbs:
        if not db.exists():
            continue
        total_size += db.stat().st_size
        with sqlite3.connect(db) as conn:
            total_trade_daily += conn.execute("select count(*) from atomic_trade_daily").fetchone()[0]
            total_trade_5m += conn.execute("select count(*) from atomic_trade_5m").fetchone()[0]

    return {
        "mode": "process_shards",
        "elapsed_sec": round(elapsed, 2),
        "ok_symbols": ok,
        "fail_symbols": fail,
        "symbols_per_min": round(ok * 60.0 / elapsed, 2) if elapsed > 0 else None,
        "db_size_mb": round(total_size / 1024 / 1024, 2),
        "trade_daily_rows": total_trade_daily,
        "trade_5m_rows": total_trade_5m,
        "worker_db_count": len(dbs),
        "error_details": error_details[:10],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day-root", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-symbols", type=int, default=160)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--exclude-gem", action="store_true")
    ap.add_argument("--main-board-only", action="store_true")
    args = ap.parse_args()

    day_root = Path(args.day_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    items = list_l2_symbol_dirs(
        day_root,
        include_bj=False,
        include_star=False,
        include_gem=not args.exclude_gem,
        main_board_only=args.main_board_only,
    )[: args.max_symbols]
    result = bench_process_shards(day_root, items, args.workers, out_root / "process_shards")
    print(
        json.dumps(
            {
                "trade_date": trade_date_from_day_root(day_root),
                "workers": args.workers,
                "max_symbols": len(items),
                "process_shards": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
