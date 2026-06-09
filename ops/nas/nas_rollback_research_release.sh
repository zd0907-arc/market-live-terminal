#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: bash ops/nas/nas_rollback_research_release.sh <archive_name>" >&2
  exit 1
fi

ARCHIVE_NAME="$1"
NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_RESEARCH_ROOT="${NAS_RESEARCH_ROOT:-$NAS_DATA_ROOT/research}"
NAS_CURRENT_ROOT="${NAS_CURRENT_ROOT:-$NAS_RESEARCH_ROOT/current}"
NAS_ARCHIVE_ROOT="${NAS_ARCHIVE_ROOT:-$NAS_RESEARCH_ROOT/archive}"
ROLLBACK_SOURCE_DIR="${ROLLBACK_SOURCE_DIR:-$NAS_ARCHIVE_ROOT/$ARCHIVE_NAME}"
FAILED_CURRENT_NAME="${FAILED_CURRENT_NAME:-failed_$(date +%Y%m%d_%H%M%S)}"
FAILED_CURRENT_DIR="${FAILED_CURRENT_DIR:-$NAS_ARCHIVE_ROOT/$FAILED_CURRENT_NAME}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e
  rollback_dir='$ROLLBACK_SOURCE_DIR'
  current_dir='$NAS_CURRENT_ROOT'
  failed_dir='$FAILED_CURRENT_DIR'

  if [ ! -d \"\$rollback_dir\" ]; then
    echo \"missing archive release: \$rollback_dir\" >&2
    exit 1
  fi

  if [ -d \"\$current_dir\" ] && [ \"\$(find \"\$current_dir\" -mindepth 1 -maxdepth 1 | head -n 1)\" ]; then
    mv \"\$current_dir\" \"\$failed_dir\"
  elif [ -d \"\$current_dir\" ]; then
    rmdir \"\$current_dir\"
  fi

  mv \"\$rollback_dir\" \"\$current_dir\"
  printf '%s\n' '$ARCHIVE_NAME' > \"\$current_dir/.rollback_from_archive\"
  printf '%s\n' \"\$(date '+%Y-%m-%d %H:%M:%S')\" > \"\$current_dir/.rolled_back_at\"

  echo \"rolled back to: $ARCHIVE_NAME\"
  echo \"current: \$current_dir\"
  if [ -d \"\$failed_dir\" ]; then
    echo \"previous current archived as failed -> \$failed_dir\"
  else
    echo 'previous current archived as failed -> none'
  fi
"
