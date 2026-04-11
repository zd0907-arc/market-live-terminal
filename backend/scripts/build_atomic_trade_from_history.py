#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DB = REPO_ROOT / 'data' / 'market_data.db'
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build atomic trade tables from existing history tables.')
    parser.add_argument('--source-db', type=Path, default=DEFAULT_SOURCE_DB, help='Source market_data.db path')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB, help='Target atomic DB path')
    parser.add_argument('--symbol', type=str, default=None, help='Optional symbol filter, e.g. sh603629')
    parser.add_argument('--date-from', type=str, default=None, help='Optional start date YYYY-MM-DD')
    parser.add_argument('--date-to', type=str, default=None, help='Optional end date YYYY-MM-DD')
    return parser.parse_args()


def build_where(alias: str, symbol: str | None, date_col: str, date_from: str | None, date_to: str | None) -> tuple[str, List[str]]:
    clauses: List[str] = []
    params: List[str] = []
    if symbol:
        clauses.append(f"{alias}.symbol = ?")
        params.append(symbol)
    if date_from:
        clauses.append(f"{alias}.{date_col} >= ?")
        params.append(date_from)
    if date_to:
        clauses.append(f"{alias}.{date_col} <= ?")
        params.append(date_to)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where_sql, params


def ensure_db_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f'{label} not found: {path}')


def load_trade_5m(conn: sqlite3.Connection, symbol: str | None, date_from: str | None, date_to: str | None) -> int:
    where_sql, params = build_where('h', symbol, 'source_date', date_from, date_to)
    sql = f"""
    INSERT OR REPLACE INTO atomic_trade_5m (
        symbol, trade_date, bucket_start, open, high, low, close,
        total_amount, total_volume, trade_count,
        l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
        l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
        l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
        l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
        source_type, quality_info, updated_at
    )
    SELECT
        h.symbol,
        h.source_date,
        h.datetime,
        h.open,
        h.high,
        h.low,
        h.close,
        h.total_amount,
        h.total_volume,
        NULL AS trade_count,
        h.l1_main_buy,
        h.l1_main_sell,
        h.l1_main_buy - h.l1_main_sell,
        h.l1_super_buy,
        h.l1_super_sell,
        h.l1_super_buy - h.l1_super_sell,
        h.l2_main_buy,
        h.l2_main_sell,
        h.l2_main_buy - h.l2_main_sell,
        h.l2_super_buy,
        h.l2_super_sell,
        h.l2_super_buy - h.l2_super_sell,
        CASE WHEN h.source_date < '2026-03-01' THEN 'trade_only' ELSE 'trade_order' END,
        h.quality_info,
        CURRENT_TIMESTAMP
    FROM source.history_5m_l2 h
    {where_sql}
    """
    cur = conn.execute(sql, params)
    return cur.rowcount if cur.rowcount != -1 else 0


def load_trade_daily(conn: sqlite3.Connection, symbol: str | None, date_from: str | None, date_to: str | None) -> int:
    where_sql_d, params_d = build_where('d', symbol, 'date', date_from, date_to)
    where_sql_h, params_h = build_where('h', symbol, 'source_date', date_from, date_to)
    if params_d != params_h:
        raise SystemExit('Internal error: daily params and 5m params diverged')

    sql = f"""
    INSERT OR REPLACE INTO atomic_trade_daily (
        symbol, trade_date, open, high, low, close,
        total_amount, total_volume, trade_count,
        l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
        l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
        l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
        l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
        l1_activity_ratio, l2_activity_ratio, l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio,
        am_l2_main_net_amount, pm_l2_main_net_amount,
        open_30m_l2_main_net_amount, last_30m_l2_main_net_amount,
        positive_l2_net_bar_count, negative_l2_net_bar_count,
        source_type, quality_info, updated_at
    )
    WITH agg AS (
        SELECT
            h.symbol,
            h.source_date AS trade_date,
            SUM(h.total_volume) AS total_volume,
            NULL AS trade_count,
            SUM(CASE WHEN time(h.datetime) < '13:00:00' THEN (h.l2_main_buy - h.l2_main_sell) ELSE 0 END) AS am_l2_main_net_amount,
            SUM(CASE WHEN time(h.datetime) >= '13:00:00' THEN (h.l2_main_buy - h.l2_main_sell) ELSE 0 END) AS pm_l2_main_net_amount,
            SUM(CASE WHEN time(h.datetime) < '10:00:00' THEN (h.l2_main_buy - h.l2_main_sell) ELSE 0 END) AS open_30m_l2_main_net_amount,
            SUM(CASE WHEN time(h.datetime) >= '14:30:00' THEN (h.l2_main_buy - h.l2_main_sell) ELSE 0 END) AS last_30m_l2_main_net_amount,
            SUM(CASE WHEN (h.l2_main_buy - h.l2_main_sell) > 0 THEN 1 ELSE 0 END) AS positive_l2_net_bar_count,
            SUM(CASE WHEN (h.l2_main_buy - h.l2_main_sell) < 0 THEN 1 ELSE 0 END) AS negative_l2_net_bar_count
        FROM source.history_5m_l2 h
        {where_sql_h}
        GROUP BY h.symbol, h.source_date
    )
    SELECT
        d.symbol,
        d.date,
        d.open,
        d.high,
        d.low,
        d.close,
        d.total_amount,
        a.total_volume,
        a.trade_count,
        d.l1_main_buy,
        d.l1_main_sell,
        d.l1_main_net,
        d.l1_super_buy,
        d.l1_super_sell,
        d.l1_super_net,
        d.l2_main_buy,
        d.l2_main_sell,
        d.l2_main_net,
        d.l2_super_buy,
        d.l2_super_sell,
        d.l2_super_net,
        d.l1_activity_ratio,
        d.l2_activity_ratio,
        d.l1_buy_ratio,
        d.l1_sell_ratio,
        d.l2_buy_ratio,
        d.l2_sell_ratio,
        a.am_l2_main_net_amount,
        a.pm_l2_main_net_amount,
        a.open_30m_l2_main_net_amount,
        a.last_30m_l2_main_net_amount,
        a.positive_l2_net_bar_count,
        a.negative_l2_net_bar_count,
        CASE WHEN d.date < '2026-03-01' THEN 'trade_only' ELSE 'trade_order' END,
        d.quality_info,
        CURRENT_TIMESTAMP
    FROM source.history_daily_l2 d
    LEFT JOIN agg a
      ON a.symbol = d.symbol AND a.trade_date = d.date
    {where_sql_d}
    """
    cur = conn.execute(sql, params_h + params_d)
    return cur.rowcount if cur.rowcount != -1 else 0


def main() -> None:
    args = parse_args()
    ensure_db_exists(args.source_db, 'Source DB')
    ensure_db_exists(args.atomic_db, 'Atomic DB')

    with sqlite3.connect(args.atomic_db) as conn:
        conn.execute(f"ATTACH DATABASE '{args.source_db}' AS source")
        rows_5m = load_trade_5m(conn, args.symbol, args.date_from, args.date_to)
        rows_daily = load_trade_daily(conn, args.symbol, args.date_from, args.date_to)
        conn.commit()
        conn.execute('DETACH DATABASE source')

    print({
        'atomic_db': str(args.atomic_db),
        'source_db': str(args.source_db),
        'symbol': args.symbol,
        'date_from': args.date_from,
        'date_to': args.date_to,
        'atomic_trade_5m_rows': rows_5m,
        'atomic_trade_daily_rows': rows_daily,
    })


if __name__ == '__main__':
    main()
