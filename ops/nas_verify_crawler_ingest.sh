#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_DB_PATH="${NAS_DB_PATH:-$NAS_DATA_ROOT/live/market_data.db}"
NAS_USER_DB_PATH="${NAS_USER_DB_PATH:-$NAS_DATA_ROOT/live/user_data.db}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "python3 - <<'PY'
import sqlite3
from pathlib import Path

db_path = Path('$NAS_DB_PATH')
user_db_path = Path('$NAS_USER_DB_PATH')
if not db_path.exists():
    raise SystemExit(f'missing market db: {db_path}')
if not user_db_path.exists():
    raise SystemExit(f'missing user db: {user_db_path}')

user_conn = sqlite3.connect(str(user_db_path))
user_cur = user_conn.cursor()
try:
    user_cur.execute('SELECT COUNT(*) FROM watchlist')
    print(f'watchlist_count: {user_cur.fetchone()[0]}')
except Exception as exc:
    print(f'watchlist_count: ERROR {exc}')
finally:
    user_conn.close()

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

checks = {
    'ticks_latest_date': 'SELECT MAX(date) FROM trade_ticks',
    'ticks_rows_latest_date': 'SELECT COUNT(*) FROM trade_ticks WHERE date = (SELECT MAX(date) FROM trade_ticks)',
    'snapshots_latest_date': 'SELECT MAX(date) FROM sentiment_snapshots',
    'snapshots_rows_latest_date': 'SELECT COUNT(*) FROM sentiment_snapshots WHERE date = (SELECT MAX(date) FROM sentiment_snapshots)',
}

for name, sql in checks.items():
    try:
        cur.execute(sql)
        print(f'{name}: {cur.fetchone()[0]}')
    except Exception as exc:
        print(f'{name}: ERROR {exc}')

conn.close()
PY"
