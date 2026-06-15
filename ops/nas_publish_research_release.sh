#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: bash ops/nas_publish_research_release.sh <release_name>" >&2
  exit 1
fi

RELEASE_NAME="$1"
NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_RESEARCH_ROOT="${NAS_RESEARCH_ROOT:-$NAS_DATA_ROOT/research}"
NAS_CURRENT_ROOT="${NAS_CURRENT_ROOT:-$NAS_RESEARCH_ROOT/current}"
NAS_STAGING_ROOT="${NAS_STAGING_ROOT:-$NAS_RESEARCH_ROOT/staging}"
NAS_ARCHIVE_ROOT="${NAS_ARCHIVE_ROOT:-$NAS_RESEARCH_ROOT/archive}"
NAS_APP_ROOT="${NAS_APP_ROOT:-/volume1/docker/market-live-terminal/app}"
RELEASE_STAGE_DIR="${RELEASE_STAGE_DIR:-$NAS_STAGING_ROOT/$RELEASE_NAME}"
ARCHIVE_NAME="${ARCHIVE_NAME:-$(date +%Y%m%d_%H%M%S)_${RELEASE_NAME}}"
ARCHIVE_TARGET_DIR="${ARCHIVE_TARGET_DIR:-$NAS_ARCHIVE_ROOT/$ARCHIVE_NAME}"
RUN_SMOKE_AFTER_PUBLISH="${RUN_SMOKE_AFTER_PUBLISH:-false}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e
  release_dir='$RELEASE_STAGE_DIR'
  current_dir='$NAS_CURRENT_ROOT'
  archive_dir='$ARCHIVE_TARGET_DIR'

  if [ ! -d \"\$release_dir\" ]; then
    echo \"missing staging release: \$release_dir\" >&2
    exit 1
  fi

  for required in atomic_facts selection market_heat; do
    if [ ! -d \"\$release_dir/\$required\" ]; then
      echo \"release missing required dir: \$release_dir/\$required\" >&2
      exit 1
    fi
  done

  mkdir -p '$NAS_ARCHIVE_ROOT'

  if [ -d \"\$current_dir\" ] && [ \"\$(find \"\$current_dir\" -mindepth 1 -maxdepth 1 | head -n 1)\" ]; then
    mv \"\$current_dir\" \"\$archive_dir\"
    bash '$NAS_APP_ROOT/ops/rewrite_market_heat_release_metadata.sh' \"\$archive_dir\" || true
  elif [ -d \"\$current_dir\" ]; then
    rmdir \"\$current_dir\"
  fi

  mkdir -p '$NAS_RESEARCH_ROOT'
  mv \"\$release_dir\" \"\$current_dir\"
  bash '$NAS_APP_ROOT/ops/rewrite_market_heat_release_metadata.sh' \"\$current_dir\"

  printf '%s\n' '$RELEASE_NAME' > \"\$current_dir/.release_name\"
  printf '%s\n' \"\$(date '+%Y-%m-%d %H:%M:%S')\" > \"\$current_dir/.published_at\"

  echo \"published: $RELEASE_NAME\"
  echo \"current: \$current_dir\"
  if [ -d \"\$archive_dir\" ]; then
    echo \"archived previous current -> \$archive_dir\"
  else
    echo 'archived previous current -> none'
  fi
"

if [ "$RUN_SMOKE_AFTER_PUBLISH" = "true" ]; then
  echo
  echo "== publish post-smoke =="
  bash ops/nas_smoke_research_release.sh
fi
