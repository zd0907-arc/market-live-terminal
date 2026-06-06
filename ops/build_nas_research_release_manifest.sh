#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: bash ops/build_nas_research_release_manifest.sh <release_name>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_NAME="$1"
FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/Desktop/AIGC/market-data}"
RESEARCH_CURRENT_ROOT_DEFAULT="$FORMAL_MARKET_DATA_ROOT/research/current"

if [ -d "$RESEARCH_CURRENT_ROOT_DEFAULT" ]; then
  SOURCE_ROOT="${SOURCE_ROOT:-$RESEARCH_CURRENT_ROOT_DEFAULT}"
  SOURCE_MODE="${SOURCE_MODE:-research_current}"
elif [ -d "$FORMAL_MARKET_DATA_ROOT" ]; then
  SOURCE_ROOT="${SOURCE_ROOT:-$FORMAL_MARKET_DATA_ROOT}"
  SOURCE_MODE="${SOURCE_MODE:-formal_root_flat}"
else
  SOURCE_ROOT="${SOURCE_ROOT:-$ROOT_DIR/data}"
  SOURCE_MODE="${SOURCE_MODE:-repo_fallback}"
fi

RUN_ROOT="${RUN_ROOT:-$ROOT_DIR/.run/nas_research_releases}"
RELEASE_RUN_DIR="$RUN_ROOT/$RELEASE_NAME"
MEMBERS_FILE="$RELEASE_RUN_DIR/release_members.txt"
MANIFEST_PATH="$RELEASE_RUN_DIR/release_manifest.json"

mkdir -p "$RELEASE_RUN_DIR"

required_members=(
  "atomic_facts/market_atomic_mainboard_compact_current.db"
  "selection/selection_research.db"
  "selection/model_feature_store.db"
  "selection/model_market_index_daily.db"
  "market_heat/fine_theme_heat_daily.db"
  "market_heat/fine_theme_heat_daily_v2.db"
  "market_heat/fine_theme_heat_forecast.db"
  "market_heat/stock_sector_map.db"
  "market_heat/tradable_theme_map.db"
  "market_heat/hot_theme_low_position_l2_samples.db"
)

optional_members=(
  "market_heat/latest.json"
  "market_heat/stock_sector_map_latest.json"
  "market_heat/sector_boards_latest.json"
  "market_heat/tradable_theme_map_latest.json"
)

missing_required=()
resolved_members=()

for rel in "${required_members[@]}"; do
  abs="$SOURCE_ROOT/$rel"
  if [ ! -f "$abs" ]; then
    missing_required+=("$rel")
    continue
  fi
  resolved_members+=("$rel")
done

if [ "${#missing_required[@]}" -gt 0 ]; then
  echo "missing required release members under $SOURCE_ROOT:" >&2
  for rel in "${missing_required[@]}"; do
    echo "  $rel" >&2
  done
  exit 1
fi

for rel in "${optional_members[@]}"; do
  abs="$SOURCE_ROOT/$rel"
  if [ -f "$abs" ]; then
    resolved_members+=("$rel")
  fi
done

cache_dir="$SOURCE_ROOT/market_heat/cache"
if [ -d "$cache_dir" ]; then
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    resolved_members+=("$rel")
  done < <(
    find "$cache_dir" -maxdepth 1 -type f -name 'fine_heat_snapshots_*_m*_*.json' \
      | sed "s#^$SOURCE_ROOT/##" \
      | sort
  )
fi

printf '%s\n' "${resolved_members[@]}" > "$MEMBERS_FILE"

SOURCE_ROOT="$SOURCE_ROOT" \
SOURCE_MODE="$SOURCE_MODE" \
RELEASE_NAME="$RELEASE_NAME" \
MEMBERS_FILE="$MEMBERS_FILE" \
MANIFEST_PATH="$MANIFEST_PATH" \
python3 - <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path

source_root = Path(os.environ["SOURCE_ROOT"]).resolve()
source_mode = os.environ["SOURCE_MODE"]
release_name = os.environ["RELEASE_NAME"]
members_file = Path(os.environ["MEMBERS_FILE"])
manifest_path = Path(os.environ["MANIFEST_PATH"])

required = {
    "atomic_facts/market_atomic_mainboard_compact_current.db",
    "selection/selection_research.db",
    "selection/model_feature_store.db",
    "selection/model_market_index_daily.db",
    "market_heat/fine_theme_heat_daily.db",
    "market_heat/fine_theme_heat_daily_v2.db",
    "market_heat/fine_theme_heat_forecast.db",
    "market_heat/stock_sector_map.db",
    "market_heat/tradable_theme_map.db",
    "market_heat/hot_theme_low_position_l2_samples.db",
}

members = [line.strip() for line in members_file.read_text(encoding="utf-8").splitlines() if line.strip()]
payload = {
    "release_name": release_name,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "source_root": str(source_root),
    "source_mode": source_mode,
    "member_count": len(members),
    "required_member_count": len(required),
    "members": [],
}

total_size = 0
for rel in members:
    path = source_root / rel
    stat = path.stat()
    total_size += int(stat.st_size)
    payload["members"].append(
        {
            "relative_path": rel,
            "required": rel in required,
            "size_bytes": int(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    )

payload["total_size_bytes"] = total_size
manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(
    {
        "release_name": release_name,
        "source_root": str(source_root),
        "source_mode": source_mode,
        "member_count": len(members),
        "total_size_bytes": total_size,
        "manifest_path": str(manifest_path),
        "members_file": str(members_file),
    },
    ensure_ascii=False,
    indent=2,
))
PY
