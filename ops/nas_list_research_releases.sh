#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_RESEARCH_ROOT="${NAS_RESEARCH_ROOT:-$NAS_DATA_ROOT/research}"
NAS_CURRENT_ROOT="${NAS_CURRENT_ROOT:-$NAS_RESEARCH_ROOT/current}"
NAS_STAGING_ROOT="${NAS_STAGING_ROOT:-$NAS_RESEARCH_ROOT/staging}"
NAS_ARCHIVE_ROOT="${NAS_ARCHIVE_ROOT:-$NAS_RESEARCH_ROOT/archive}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e

  describe_dir() {
    local label=\"\$1\"
    local dir=\"\$2\"
    echo \"=== \$label ===\"
    if [ ! -d \"\$dir\" ]; then
      echo '(missing)'
      return
    fi
    find \"\$dir\" -mindepth 1 -maxdepth 1 -type d -print | sort || true
  }

  echo '=== current ==='
  if [ -d '$NAS_CURRENT_ROOT' ]; then
    ls -ld '$NAS_CURRENT_ROOT'
    for meta in .release_name .published_at .rollback_from_archive .rolled_back_at; do
      if [ -f '$NAS_CURRENT_ROOT/'\"\$meta\" ]; then
        echo \"\$meta: \$(cat '$NAS_CURRENT_ROOT/'\"\$meta\")\"
      fi
    done
  else
    echo '(missing)'
  fi
  echo
  describe_dir 'staging releases' '$NAS_STAGING_ROOT'
  echo
  describe_dir 'archive releases' '$NAS_ARCHIVE_ROOT'
"
