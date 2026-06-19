#!/usr/bin/env bash
set -euo pipefail

NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
SNAPSHOT_PROFILE="${SNAPSHOT_PROFILE:-runtime}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"

case "$SNAPSHOT_PROFILE" in
  runtime|light)
    SNAPSHOT_PROFILE="runtime"
    BACKUP_ROOT="${BACKUP_ROOT:-/volume1/docker/market-live-terminal/backups/runtime_snapshots}"
    INCLUDE_ATOMIC="${INCLUDE_ATOMIC:-0}"
    RETENTION_COUNT="${RETENTION_COUNT:-4}"
    ;;
  full|atomic)
    SNAPSHOT_PROFILE="full"
    BACKUP_ROOT="${BACKUP_ROOT:-/volume1/docker/market-live-terminal/backups/full_snapshots}"
    INCLUDE_ATOMIC="${INCLUDE_ATOMIC:-1}"
    RETENTION_COUNT="${RETENTION_COUNT:-1}"
    ;;
  *)
    echo "unsupported SNAPSHOT_PROFILE: $SNAPSHOT_PROFILE (expected runtime or full)" >&2
    exit 2
    ;;
esac

TARGET_ROOT="${BACKUP_ROOT}/${STAMP}"

mkdir -p "$TARGET_ROOT/live"
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
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/selection_research.db" "${TARGET_ROOT}/research/current/selection/selection_research.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/model_feature_store.db" "${TARGET_ROOT}/research/current/selection/model_feature_store.db"
backup_sqlite "${NAS_DATA_ROOT}/research/current/selection/model_market_index_daily.db" "${TARGET_ROOT}/research/current/selection/model_market_index_daily.db"

if [ "$INCLUDE_ATOMIC" = "1" ]; then
  mkdir -p "$TARGET_ROOT/research/current/atomic_facts"
  backup_sqlite "${NAS_DATA_ROOT}/research/current/atomic_facts/market_atomic_mainboard_compact_current.db" "${TARGET_ROOT}/research/current/atomic_facts/market_atomic_mainboard_compact_current.db"
fi

while IFS= read -r heat_db; do
  [ -n "$heat_db" ] || continue
  backup_sqlite "$heat_db" "${TARGET_ROOT}/research/current/market_heat/$(basename "$heat_db")"
done < <(find "${NAS_DATA_ROOT}/research/current/market_heat" -maxdepth 1 -type f -name '*.db' | sort)

find "${NAS_DATA_ROOT}/research/current/market_heat" -maxdepth 1 -type f -name '*_latest.json' -exec cp {} "${TARGET_ROOT}/research/current/market_heat/" \;

cat > "${TARGET_ROOT}/manifest.txt" <<EOF
timestamp=${STAMP}
snapshot_profile=${SNAPSHOT_PROFILE}
nas_data_root=${NAS_DATA_ROOT}
backup_root=${BACKUP_ROOT}
include_atomic=${INCLUDE_ATOMIC}
retention_count=${RETENTION_COUNT}
EOF

prune_old_snapshots() {
  local retention="$1"
  local backup_root="$2"
  if ! [[ "$retention" =~ ^[0-9]+$ ]] || [ "$retention" -le 0 ]; then
    return 0
  fi
  local snapshot_dirs=()
  local snapshot_dir
  while IFS= read -r snapshot_dir; do
    snapshot_dirs+=("$snapshot_dir")
  done < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
  local total="${#snapshot_dirs[@]}"
  local remove_count=$((total - retention))
  if [ "$remove_count" -le 0 ]; then
    return 0
  fi
  local index=0
  while [ "$index" -lt "$remove_count" ]; do
    rm -rf "${backup_root}/${snapshot_dirs[$index]}"
    index=$((index + 1))
  done
}

prune_old_snapshots "$RETENTION_COUNT" "$BACKUP_ROOT"

echo "TARGET_ROOT=${TARGET_ROOT}"
