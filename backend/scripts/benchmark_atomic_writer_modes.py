#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.run_atomic_backfill_windows import ensure_atomic_db, list_l2_symbol_dirs, process_l2_symbol


def trade_date_from_day_root(day_root: Path) -> str:
    name = day_root.name
    return f'{name[:4]}-{name[4:6]}-{name[6:]}'


def summarize_db(mode: str, db: Path, ok: int, fail: int, elapsed: float) -> Dict[str, object]:
    with sqlite3.connect(db) as conn:
        trade_daily = conn.execute('select count(*) from atomic_trade_daily').fetchone()[0]
        trade_5m = conn.execute('select count(*) from atomic_trade_5m').fetchone()[0]
    return {
        'mode': mode,
        'elapsed_sec': round(elapsed, 2),
        'ok_symbols': ok,
        'fail_symbols': fail,
        'symbols_per_min': round(ok * 60.0 / elapsed, 2) if elapsed > 0 else None,
        'db_size_mb': round(db.stat().st_size / 1024 / 1024, 2) if db.exists() else 0,
        'trade_daily_rows': trade_daily,
        'trade_5m_rows': trade_5m,
    }


def bench_single_db(day_root: Path, items: Sequence[Path], workers: int, out_db: Path) -> Dict[str, object]:
    if out_db.exists():
        out_db.unlink()
    ensure_atomic_db(out_db)
    lock = threading.Lock()
    started = time.perf_counter()
    ok = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(process_l2_symbol, item, trade_date_from_day_root(day_root), out_db, lock, 200000.0, 1000000.0)
            for item in items
        ]
        for f in as_completed(futures):
            try:
                f.result()
                ok += 1
            except Exception:
                fail += 1
    elapsed = time.perf_counter() - started
    return summarize_db('single_db', out_db, ok, fail, elapsed)


def _worker_shard(shard_items: Sequence[Path], day_root: Path, out_db: Path) -> Dict[str, int]:
    if out_db.exists():
        out_db.unlink()
    ensure_atomic_db(out_db)
    lock = threading.Lock()
    ok = 0
    fail = 0
    for item in shard_items:
        try:
            process_l2_symbol(item, trade_date_from_day_root(day_root), out_db, lock, 200000.0, 1000000.0)
            ok += 1
        except Exception:
            fail += 1
    return {'ok': ok, 'fail': fail}


def bench_worker_dbs(day_root: Path, items: Sequence[Path], workers: int, out_dir: Path) -> Dict[str, object]:
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    shards = [list(items[i::workers]) for i in range(workers)]
    started = time.perf_counter()
    ok = 0
    fail = 0
    dbs: List[Path] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        for idx, shard in enumerate(shards, start=1):
            if not shard:
                continue
            db = out_dir / f'worker_{idx}.db'
            dbs.append(db)
            futures[ex.submit(_worker_shard, shard, day_root, db)] = idx
        for f in as_completed(futures):
            r = f.result()
            ok += int(r['ok'])
            fail += int(r['fail'])
    elapsed = time.perf_counter() - started
    total_size = sum(db.stat().st_size for db in dbs if db.exists())
    total_trade_daily = 0
    total_trade_5m = 0
    for db in dbs:
        if not db.exists():
            continue
        with sqlite3.connect(db) as conn:
            total_trade_daily += conn.execute('select count(*) from atomic_trade_daily').fetchone()[0]
            total_trade_5m += conn.execute('select count(*) from atomic_trade_5m').fetchone()[0]
    return {
        'mode': 'worker_dbs',
        'elapsed_sec': round(elapsed, 2),
        'ok_symbols': ok,
        'fail_symbols': fail,
        'symbols_per_min': round(ok * 60.0 / elapsed, 2) if elapsed > 0 else None,
        'db_size_mb': round(total_size / 1024 / 1024, 2),
        'trade_daily_rows': total_trade_daily,
        'trade_5m_rows': total_trade_5m,
        'worker_db_count': len(dbs),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--day-root', required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--max-symbols', type=int, default=80)
    ap.add_argument('--out-root', required=True)
    args = ap.parse_args()

    day_root = Path(args.day_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    items = list_l2_symbol_dirs(day_root, include_bj=False, include_star=False)[: args.max_symbols]
    single = bench_single_db(day_root, items, args.workers, out_root / 'single.db')
    worker = bench_worker_dbs(day_root, items, args.workers, out_root / 'worker_dbs')
    print(json.dumps({
        'trade_date': trade_date_from_day_root(day_root),
        'workers': args.workers,
        'max_symbols': len(items),
        'single_db': single,
        'worker_dbs': worker,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
