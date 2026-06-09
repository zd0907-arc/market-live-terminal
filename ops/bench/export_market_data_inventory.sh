#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/Desktop/AIGC/market-data}"
MARKET_DATA_ROOT="${MARKET_DATA_ROOT:-$FORMAL_MARKET_DATA_ROOT}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.run/market-data-inventory}"

mkdir -p "$OUT_DIR"

find "$MARKET_DATA_ROOT" -maxdepth 3 -type f \( -name '*.db' -o -name '*.json' -o -name '*.csv' -o -name '*.joblib' -o -name '*.md' \) | sort > "$OUT_DIR/market_data_files.txt"
find "$MARKET_DATA_ROOT" -maxdepth 3 -type f -name '*.db' -exec ls -lh {} + | sort -k9 > "$OUT_DIR/market_data_dbs.txt"
find "$MARKET_DATA_ROOT" -maxdepth 3 -type d | sort > "$OUT_DIR/market_data_dirs.txt"
find "$MARKET_DATA_ROOT" -maxdepth 4 -type l | sort > "$OUT_DIR/market_data_symlinks.txt"
find "$MARKET_DATA_ROOT" -maxdepth 4 \( -name '*.db-wal' -o -name '*.db-shm' \) | sort > "$OUT_DIR/market_data_runtime_residue.txt"

find "$ROOT_DIR/data" -maxdepth 4 -type f \( -name '*.db' -o -name '*.json' -o -name '*.csv' -o -name '*.joblib' -o -name '*.md' \) | sort > "$OUT_DIR/repo_data_files.txt"
find "$ROOT_DIR/data" -type f -name '*.db' -exec ls -lh {} + | sort -k9 > "$OUT_DIR/repo_data_dbs.txt"
find "$ROOT_DIR/data" -maxdepth 4 -type d | sort > "$OUT_DIR/repo_data_dirs.txt"
find "$ROOT_DIR/data" -maxdepth 4 \( -name '*.db-wal' -o -name '*.db-shm' \) | sort > "$OUT_DIR/repo_data_runtime_residue.txt"

echo "inventory exported to $OUT_DIR"
