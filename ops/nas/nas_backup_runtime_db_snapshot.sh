#!/usr/bin/env bash
set -euo pipefail

NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
BACKUP_ROOT="${BACKUP_ROOT:-/volume1/docker/market-live-terminal/backups/db_snapshots}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
TARGET_ROOT="${BACKUP_ROOT}/${STAMP}"

mkdir -p "$TARGET_ROOT/live"
mkdir -p "$TARGET_ROOT/research/current/atomic_facts"
mkdir -p "$TARGET_ROOT/research/current/selection"
mkdir -p "$TARGET_ROOT/research/current/market_heat"

backup_sqlite() {
  local src="$1"
  local dst="$2"
  if [ ! -f "$src" ]; then
    return 0
  fi
  sqlite3 "$src" ".backup '$dst'"
}

backup_sqlite "${NAS_DATA_ROOT}/live/market_data.db" "${TARGET_ROOT}/live/market_data.db"
backup_sqlite "${NAS_DATA_ROOT}/live/user_data.db" "${TARGET_ROOT}/live/user_data.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/atomic_facts/market_atomic_mainboard_compact_current.db" "${TARGET_ROOT}/research/current/atomic_facts/market_atomic_mainboard_compact_current.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/selection_research.db" "${TARGET_ROOT}/research/current/selection/selection_research.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/model_feature_store.db" "${TARGET_ROOT}/research/current/selection/model_feature_store.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/model_market_index_daily.db" "${TARGET_ROOT}/research/current/selection/model_market_index_daily.db"

while IFS= read -r heat_db; do
  [ -n "$heat_db" ] || continue
  backup_sqlite "$heat_db" "${TARGET_ROOT}/research/current/market_heat/$(basename "$heat_db")"
done < <(find "${NAS_DATA_ROOT}/research/current/market_heat" -maxdepth 1 -type f -name '*.db' | sort)

find "${NAS_DATA_ROOT}/research/current/market_heat" -maxdepth 1 -type f -name '*_latest.json' -exec cp {} "${TARGET_ROOT}/research/current/market_heat/" \;

cat > "${TARGET_ROOT}/manifest.txt" <<EOF
timestamp=${STAMP}
nas_data_root=${NAS_DATA_ROOT}
backup_root=${BACKUP_ROOT}
EOF

echo "TARGET_ROOT=${TARGET_ROOT}"
