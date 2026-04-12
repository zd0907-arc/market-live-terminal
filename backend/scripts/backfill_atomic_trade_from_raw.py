#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import is_symbol_dir, normalize_month_day_root

REPO_ROOT = Path(ROOT_DIR)
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'


def normalize_symbol_dir_name(name: str) -> str:
    raw = (name or '').strip().lower()
    if len(raw) == 9 and raw[6] == '.':
        market = raw[7:]
        code = raw[:6]
        if market in {'sz', 'sh', 'bj'}:
            return f'{market}{code}'
    return raw


def list_symbol_dirs(day_root: Path, symbols: Optional[Sequence[str]] = None) -> List[Path]:
    targets = {s.lower() for s in symbols} if symbols else None
    result: List[Path] = []
    for child in sorted(day_root.iterdir()):
        if not child.is_dir():
            continue
        if not re.fullmatch(r'\d{6}\.(SZ|SH|BJ)', child.name, re.I):
            continue
        normalized = normalize_symbol_dir_name(child.name)
        if targets and normalized not in targets:
            continue
        result.append(child)
    return result


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding='gb18030', low_memory=False)
    bad_cols = [c for c in df.columns if str(c).strip() == '' or str(c).startswith('Unnamed')]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _format_trade_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ':' + hhmmss.str[2:4] + ':' + hhmmss.str[4:6]


def _resolve_day_root(input_path: Path) -> Tuple[Path, str, List[Path]]:
    if is_symbol_dir(input_path):
        return input_path.parent, input_path.parent.name, [input_path]
    if input_path.is_dir() and (input_path / '逐笔成交.csv').is_file():
        return input_path.parent, input_path.parent.name, [input_path]
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date, []


def _canonical_trade_date(raw: str) -> str:
    text = (raw or '').strip()
    if len(text) == 8 and text.isdigit():
        return f'{text[:4]}-{text[4:6]}-{text[6:]}'
    return text


def _build_trade_metrics(symbol_dir: Path, trade_date: str) -> Tuple[List[Tuple[str, str, float, int]], Tuple[str, str, float, int]]:
    trade = _read_csv(symbol_dir / '逐笔成交.csv')
    required = ['时间', '成交价格', '成交数量']
    missing = [c for c in required if c not in trade.columns]
    if missing:
        raise ValueError(f'逐笔成交缺列: {", ".join(missing)}')

    ticks = pd.DataFrame()
    ticks['time'] = _format_trade_time(trade['时间'])
    ticks['datetime'] = pd.to_datetime(f'{trade_date} ' + ticks['time'], errors='coerce')
    ticks['price'] = pd.to_numeric(trade['成交价格'], errors='coerce') / 10000
    ticks['volume'] = pd.to_numeric(trade['成交数量'], errors='coerce')
    ticks = ticks.dropna(subset=['datetime', 'price', 'volume'])
    ticks = ticks[(ticks['price'] > 0) & (ticks['volume'] > 0)]

    session_time = ticks['datetime'].dt.strftime('%H:%M:%S')
    trading_mask = ((session_time >= '09:30:00') & (session_time <= '11:30:00')) | (
        (session_time >= '13:00:00') & (session_time <= '15:00:00')
    )
    ticks = ticks[trading_mask].sort_values('datetime').reset_index(drop=True)
    if ticks.empty:
        return [], (normalize_symbol_dir_name(symbol_dir.name), _canonical_trade_date(trade_date), 0.0, 0)

    ticks['bucket'] = ticks['datetime'].dt.floor('5min')
    agg_5m = ticks.groupby('bucket').agg(total_volume=('volume', 'sum'), trade_count=('volume', 'size')).reset_index()
    symbol = normalize_symbol_dir_name(symbol_dir.name)
    trade_date_canonical = _canonical_trade_date(trade_date)
    rows_5m = [
        (
            symbol,
            row['bucket'].strftime('%Y-%m-%d %H:%M:%S'),
            float(row['total_volume']),
            int(row['trade_count']),
        )
        for _, row in agg_5m.iterrows()
    ]
    daily = (symbol, trade_date_canonical, float(ticks['volume'].sum()), int(len(ticks)))
    return rows_5m, daily


def _update_atomic(conn: sqlite3.Connection, rows_5m: List[Tuple[str, str, float, int]], daily: Tuple[str, str, float, int]) -> Dict[str, int]:
    updated_5m = 0
    missing_5m = 0
    for symbol, bucket_start, total_volume, trade_count in rows_5m:
        cur = conn.execute(
            """
            UPDATE atomic_trade_5m
            SET total_volume = ?, trade_count = ?, updated_at = CURRENT_TIMESTAMP
            WHERE symbol = ? AND bucket_start = ?
            """,
            (total_volume, trade_count, symbol, bucket_start),
        )
        if cur.rowcount:
            updated_5m += int(cur.rowcount)
        else:
            missing_5m += 1

    symbol, trade_date, total_volume, trade_count = daily
    cur = conn.execute(
        """
        UPDATE atomic_trade_daily
        SET total_volume = ?, trade_count = ?, updated_at = CURRENT_TIMESTAMP
        WHERE symbol = ? AND trade_date = ?
        """,
        (total_volume, trade_count, symbol, trade_date),
    )
    updated_daily = int(cur.rowcount or 0)
    missing_daily = 0 if updated_daily else 1

    return {
        'updated_5m': updated_5m,
        'missing_5m': missing_5m,
        'updated_daily': updated_daily,
        'missing_daily': missing_daily,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backfill atomic trade total_volume/trade_count from raw trade CSVs.')
    parser.add_argument('input_path', help='Day root or symbol dir')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument('--symbols', default='', help='Comma-separated symbols like sh603629,sz000833')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.atomic_db.exists():
        raise SystemExit(f'Atomic DB not found: {args.atomic_db}')

    day_root, trade_date, preselected = _resolve_day_root(Path(args.input_path))
    symbols = [s.strip().lower() for s in args.symbols.split(',') if s.strip()]
    symbol_dirs = preselected or list_symbol_dirs(day_root, symbols=symbols or None)
    if args.limit > 0:
        symbol_dirs = symbol_dirs[:args.limit]

    results = []
    failures = []
    with sqlite3.connect(args.atomic_db) as conn:
        for symbol_dir in symbol_dirs:
            try:
                rows_5m, daily = _build_trade_metrics(symbol_dir, trade_date)
                update_stats = {'updated_5m': 0, 'missing_5m': 0, 'updated_daily': 0, 'missing_daily': 0}
                if not args.dry_run:
                    update_stats = _update_atomic(conn, rows_5m, daily)
                results.append({
                    'symbol': normalize_symbol_dir_name(symbol_dir.name),
                    'trade_date': _canonical_trade_date(trade_date),
                    'raw_5m_rows': len(rows_5m),
                    'raw_daily_trade_count': daily[3],
                    'raw_daily_total_volume': daily[2],
                    **update_stats,
                })
            except Exception as exc:
                failures.append({'symbol': normalize_symbol_dir_name(symbol_dir.name), 'error': str(exc)})
        if not args.dry_run:
            conn.commit()

    print({
        'input_path': str(args.input_path),
        'resolved_day_root': str(day_root),
        'trade_date': _canonical_trade_date(trade_date),
        'processed_count': len(results),
        'failure_count': len(failures),
        'results': results[:20],
        'failures': failures[:20],
        'dry_run': bool(args.dry_run),
        'atomic_db': str(args.atomic_db),
    })


if __name__ == '__main__':
    main()
