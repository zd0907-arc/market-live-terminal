#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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

from backend.scripts.run_atomic_backfill_windows import ensure_atomic_db, list_l2_symbol_dirs, normalize_symbol_dir_name
from backend.scripts.run_atomic_backfill_windows import (
    _build_atomic_trade_5m_rows_from_l2,
    _build_atomic_trade_daily_row,
)
from backend.scripts.backfill_atomic_order_from_raw import _apply_support_ratios, _build_order_rows, _replace_rows as replace_order_rows
from backend.scripts.build_book_state_from_raw import build_book_rows, replace_book_rows
from backend.scripts.build_open_auction_summaries import _build_l1_summary, _build_l2_summary, _build_phase_l1_summary, _build_phase_l2_summary, _build_manifest, _upsert as upsert_auction
from backend.scripts.run_atomic_backfill_windows import _replace_trade_rows


class Metrics:
    def __init__(self) -> None:
        self.symbols = 0
        self.failures = 0
        self.build_trade_sec = 0.0
        self.build_order_sec = 0.0
        self.build_book_sec = 0.0
        self.build_auction_sec = 0.0
        self.write_sec = 0.0
        self.lock_wait_sec = 0.0
        self.commit_count = 0

    def add(self, other: 'Metrics') -> None:
        self.symbols += other.symbols
        self.failures += other.failures
        self.build_trade_sec += other.build_trade_sec
        self.build_order_sec += other.build_order_sec
        self.build_book_sec += other.build_book_sec
        self.build_auction_sec += other.build_auction_sec
        self.write_sec += other.write_sec
        self.lock_wait_sec += other.lock_wait_sec
        self.commit_count += other.commit_count

    def to_dict(self) -> Dict[str, float]:
        return {
            'symbols': self.symbols,
            'failures': self.failures,
            'build_trade_sec': round(self.build_trade_sec, 3),
            'build_order_sec': round(self.build_order_sec, 3),
            'build_book_sec': round(self.build_book_sec, 3),
            'build_auction_sec': round(self.build_auction_sec, 3),
            'write_sec': round(self.write_sec, 3),
            'lock_wait_sec': round(self.lock_wait_sec, 3),
            'commit_count': self.commit_count,
        }


def trade_date_from_day_root(day_root: Path) -> str:
    name = day_root.name
    return f'{name[:4]}-{name[4:6]}-{name[6:]}'


def build_payload(symbol_dir: Path, trade_date: str, metrics: Metrics) -> Dict[str, object]:
    t0 = time.perf_counter()
    rows_5m_trade, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_l2(symbol_dir, trade_date, 200000.0, 1000000.0)
    daily_trade = _build_atomic_trade_daily_row(normalize_symbol_dir_name(symbol_dir.name), trade_date, rows_5m_trade, 'trade_order', quality_info, daily_feature)
    metrics.build_trade_sec += time.perf_counter() - t0

    t1 = time.perf_counter()
    _, rows_5m_order, daily_order, _ = _build_order_rows(symbol_dir, trade_date)
    metrics.build_order_sec += time.perf_counter() - t1

    t2 = time.perf_counter()
    rows_5m_book, daily_book = build_book_rows(symbol_dir, trade_date)
    metrics.build_book_sec += time.perf_counter() - t2

    t3 = time.perf_counter()
    compact = trade_date.replace('-', '')
    l1_row = _build_l1_summary(symbol_dir, compact)
    l2_row = _build_l2_summary(symbol_dir, compact)
    phase_l1_row = _build_phase_l1_summary(symbol_dir, compact)
    phase_l2_row = _build_phase_l2_summary(symbol_dir, compact)
    manifest = _build_manifest(l1_row, l2_row)
    metrics.build_auction_sec += time.perf_counter() - t3

    return {
        'rows_5m_trade': rows_5m_trade,
        'daily_trade': daily_trade,
        'rows_5m_order': rows_5m_order,
        'daily_order': daily_order,
        'rows_5m_book': rows_5m_book,
        'daily_book': daily_book,
        'l1_row': l1_row,
        'l2_row': l2_row,
        'phase_l1_row': phase_l1_row,
        'phase_l2_row': phase_l2_row,
        'manifest': manifest,
    }


def write_payload(conn: sqlite3.Connection, payload: Dict[str, object]) -> None:
    daily_trade = payload['daily_trade']
    trade_stats = _replace_trade_rows(conn, payload['rows_5m_trade'], daily_trade) if daily_trade else {'rows_5m': 0, 'rows_daily': 0}
    total_amount = float(daily_trade[6]) if daily_trade else None
    daily_order = _apply_support_ratios(payload['daily_order'], total_amount)
    replace_order_rows(conn, payload['rows_5m_order'], daily_order)
    replace_book_rows(conn, payload['rows_5m_book'], payload['daily_book'])
    upsert_auction(conn, 'atomic_open_auction_l1_daily', payload['l1_row'])
    upsert_auction(conn, 'atomic_open_auction_l2_daily', payload['l2_row'])
    upsert_auction(conn, 'atomic_open_auction_phase_l1_daily', payload['phase_l1_row'])
    upsert_auction(conn, 'atomic_open_auction_phase_l2_daily', payload['phase_l2_row'])
    upsert_auction(conn, 'atomic_open_auction_manifest', payload['manifest'])


def bench_current_like(items: Sequence[Path], trade_date: str, db_path: Path, workers: int) -> Dict[str, object]:
    if db_path.exists():
        db_path.unlink()
    ensure_atomic_db(db_path)
    lock = threading.Lock()
    started = time.perf_counter()

    def worker(item: Path) -> Metrics:
        m = Metrics()
        try:
            payload = build_payload(item, trade_date, m)
            wait0 = time.perf_counter()
            with lock:
                m.lock_wait_sec += time.perf_counter() - wait0
                t = time.perf_counter()
                with sqlite3.connect(db_path) as conn:
                    write_payload(conn, payload)
                    conn.commit()
                m.write_sec += time.perf_counter() - t
                m.commit_count += 1
            m.symbols += 1
        except Exception:
            m.failures += 1
        return m

    total = Metrics()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(worker, item) for item in items]):
            total.add(f.result())
    elapsed = time.perf_counter() - started
    return summarize('current_like', db_path, total, elapsed)


def bench_batch_commit(items: Sequence[Path], trade_date: str, db_path: Path, workers: int, batch_size: int) -> Dict[str, object]:
    if db_path.exists():
        db_path.unlink()
    ensure_atomic_db(db_path)
    lock = threading.Lock()
    shards = [list(items[i::workers]) for i in range(workers)]
    started = time.perf_counter()

    def worker(shard: Sequence[Path]) -> Metrics:
        m = Metrics()
        payloads: List[Dict[str, object]] = []
        conn = sqlite3.connect(db_path)
        try:
            for item in shard:
                try:
                    payloads.append(build_payload(item, trade_date, m))
                    m.symbols += 1
                    if len(payloads) >= batch_size:
                        wait0 = time.perf_counter()
                        with lock:
                            m.lock_wait_sec += time.perf_counter() - wait0
                            t = time.perf_counter()
                            for payload in payloads:
                                write_payload(conn, payload)
                            conn.commit()
                            m.commit_count += 1
                            m.write_sec += time.perf_counter() - t
                        payloads.clear()
                except Exception:
                    m.failures += 1
            if payloads:
                wait0 = time.perf_counter()
                with lock:
                    m.lock_wait_sec += time.perf_counter() - wait0
                    t = time.perf_counter()
                    for payload in payloads:
                        write_payload(conn, payload)
                    conn.commit()
                    m.commit_count += 1
                    m.write_sec += time.perf_counter() - t
        finally:
            conn.close()
        return m

    total = Metrics()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(worker, shard) for shard in shards if shard]):
            total.add(f.result())
    elapsed = time.perf_counter() - started
    return summarize(f'batch_commit_{batch_size}', db_path, total, elapsed)


def summarize(mode: str, db_path: Path, metrics: Metrics, elapsed: float) -> Dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        trade_daily = conn.execute('select count(*) from atomic_trade_daily').fetchone()[0]
        order_daily = conn.execute('select count(*) from atomic_order_daily').fetchone()[0]
        book_daily = conn.execute('select count(*) from atomic_book_state_daily').fetchone()[0]
    return {
        'mode': mode,
        'elapsed_sec': round(elapsed, 2),
        'symbols_per_min': round(metrics.symbols * 60.0 / elapsed, 2) if elapsed > 0 else None,
        'db_size_mb': round(db_path.stat().st_size / 1024 / 1024, 2),
        'trade_daily_rows': trade_daily,
        'order_daily_rows': order_daily,
        'book_daily_rows': book_daily,
        'metrics': metrics.to_dict(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--day-root', required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--max-symbols', type=int, default=24)
    ap.add_argument('--batch-size', type=int, default=4)
    ap.add_argument('--out-root', required=True)
    args = ap.parse_args()

    day_root = Path(args.day_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    items = list_l2_symbol_dirs(day_root, include_bj=False, include_star=False)[: args.max_symbols]
    trade_date = trade_date_from_day_root(day_root)
    current = bench_current_like(items, trade_date, out_root / 'current_like.db', args.workers)
    batch = bench_batch_commit(items, trade_date, out_root / 'batch_commit.db', args.workers, args.batch_size)
    print(json.dumps({
        'trade_date': trade_date,
        'workers': args.workers,
        'max_symbols': len(items),
        'current_like': current,
        'batch_commit': batch,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
