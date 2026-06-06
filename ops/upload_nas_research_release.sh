#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: bash ops/upload_nas_research_release.sh <release_name>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_NAME="$1"
FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/Desktop/AIGC/market-data}"
RESEARCH_CURRENT_ROOT_DEFAULT="$FORMAL_MARKET_DATA_ROOT/research/current"

if [ -d "$RESEARCH_CURRENT_ROOT_DEFAULT" ]; then
  SOURCE_ROOT="${SOURCE_ROOT:-$RESEARCH_CURRENT_ROOT_DEFAULT}"
else
  SOURCE_ROOT="${SOURCE_ROOT:-$FORMAL_MARKET_DATA_ROOT}"
fi

RUN_ROOT="${RUN_ROOT:-$ROOT_DIR/.run/nas_research_releases}"
RELEASE_RUN_DIR="$RUN_ROOT/$RELEASE_NAME"
MEMBERS_FILE="$RELEASE_RUN_DIR/release_members.txt"
MANIFEST_PATH="$RELEASE_RUN_DIR/release_manifest.json"

NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_STAGING_ROOT="${NAS_STAGING_ROOT:-$NAS_DATA_ROOT/research/staging}"
NAS_RELEASE_DIR="${NAS_RELEASE_DIR:-$NAS_STAGING_ROOT/$RELEASE_NAME}"
NAS_APP_ROOT="${NAS_APP_ROOT:-/volume1/docker/market-live-terminal/app}"
UPLOAD_MODE="${UPLOAD_MODE:-scp}"
SCP_PROTOCOL_OPT="${SCP_PROTOCOL_OPT:--O}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-8}"

SSH_ARGS=(
  -o
  "ConnectTimeout=$SSH_CONNECT_TIMEOUT"
)

SCP_ARGS=(
  "$SCP_PROTOCOL_OPT"
  -o
  "ConnectTimeout=$SSH_CONNECT_TIMEOUT"
)

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh
if [ "$UPLOAD_MODE" = "rsync" ]; then
  require_cmd rsync
else
  require_cmd scp
fi

if [ ! -f "$MEMBERS_FILE" ] || [ ! -f "$MANIFEST_PATH" ]; then
  bash "$ROOT_DIR/ops/build_nas_research_release_manifest.sh" "$RELEASE_NAME" >/dev/null
fi

if [ ! -f "$MEMBERS_FILE" ] || [ ! -f "$MANIFEST_PATH" ]; then
  echo "release manifest not found: $RELEASE_RUN_DIR" >&2
  exit 1
fi

ssh "${SSH_ARGS[@]}" "$NAS_HOST" "
  set -e
  rm -rf '$NAS_RELEASE_DIR'
  mkdir -p '$NAS_RELEASE_DIR'
"

if [ "$UPLOAD_MODE" = "rsync" ]; then
  rsync \
    -av \
    --files-from="$MEMBERS_FILE" \
    "$SOURCE_ROOT/" \
    "$NAS_HOST:$NAS_RELEASE_DIR/"
else
  DIR_ARGS="$(
    MEMBERS_FILE="$MEMBERS_FILE" NAS_RELEASE_DIR="$NAS_RELEASE_DIR" python3 - <<'PY'
import os
import shlex
from pathlib import Path

members_file = Path(os.environ["MEMBERS_FILE"])
release_dir = os.environ["NAS_RELEASE_DIR"].rstrip("/")
dirs = sorted(
    {
        str(Path(line.strip()).parent)
        for line in members_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and str(Path(line.strip()).parent) != "."
    }
)
quoted = [shlex.quote(release_dir)]
quoted.extend(shlex.quote(f"{release_dir}/{rel_dir}") for rel_dir in dirs)
print(" ".join(quoted))
PY
  )"

  ssh "${SSH_ARGS[@]}" "$NAS_HOST" "mkdir -p $DIR_ARGS"

  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    scp "${SCP_ARGS[@]}" "$SOURCE_ROOT/$rel" "$NAS_HOST:$NAS_RELEASE_DIR/$rel"
  done < "$MEMBERS_FILE"
fi

scp "${SCP_ARGS[@]}" "$MANIFEST_PATH" "$NAS_HOST:$NAS_RELEASE_DIR/release_manifest.json"

ssh "${SSH_ARGS[@]}" "$NAS_HOST" "
  set -e
  bash '$NAS_APP_ROOT/ops/rewrite_market_heat_release_metadata.sh' '$NAS_RELEASE_DIR'
"

ssh "${SSH_ARGS[@]}" "$NAS_HOST" "
  set -e
  if [ ! -f '$NAS_RELEASE_DIR/atomic_facts/market_atomic_mainboard_compact_current.db' ]; then
    echo 'missing atomic db after upload' >&2
    exit 1
  fi
  if [ ! -f '$NAS_RELEASE_DIR/selection/selection_research.db' ]; then
    echo 'missing selection db after upload' >&2
    exit 1
  fi
  if [ ! -f '$NAS_RELEASE_DIR/market_heat/fine_theme_heat_daily_v2.db' ]; then
    echo 'missing market heat v2 db after upload' >&2
    exit 1
  fi
  echo 'uploaded release staging:'
  echo '  dir=$NAS_RELEASE_DIR'
  echo '  manifest='
  ls -lh '$NAS_RELEASE_DIR/release_manifest.json'
"
