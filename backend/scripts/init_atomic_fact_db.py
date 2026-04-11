#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'
DEFAULT_SCHEMA = REPO_ROOT / 'backend' / 'scripts' / 'sql' / 'atomic_fact_p0_schema.sql'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Initialize atomic fact SQLite database from schema SQL.')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB, help='Target atomic DB path')
    parser.add_argument('--schema', type=Path, default=DEFAULT_SCHEMA, help='Schema SQL path')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.atomic_db.parent.mkdir(parents=True, exist_ok=True)

    if not args.schema.exists():
        raise SystemExit(f'Schema file not found: {args.schema}')

    sql = args.schema.read_text(encoding='utf-8')
    with sqlite3.connect(args.atomic_db) as conn:
        conn.executescript(sql)
        conn.commit()

    print(f'Initialized atomic DB: {args.atomic_db}')


if __name__ == '__main__':
    main()
