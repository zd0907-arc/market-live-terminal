#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_LIVE_ROOT="${NAS_LIVE_ROOT:-$NAS_DATA_ROOT/live}"
NAS_RESEARCH_ROOT="${NAS_RESEARCH_ROOT:-$NAS_DATA_ROOT/research}"
NAS_CURRENT_ROOT="${NAS_CURRENT_ROOT:-$NAS_RESEARCH_ROOT/current}"
NAS_STAGING_ROOT="${NAS_STAGING_ROOT:-$NAS_RESEARCH_ROOT/staging}"
NAS_ARCHIVE_ROOT="${NAS_ARCHIVE_ROOT:-$NAS_RESEARCH_ROOT/archive}"
NAS_CACHE_ROOT="${NAS_CACHE_ROOT:-$NAS_DATA_ROOT/cache}"
NAS_ARTIFACTS_ROOT="${NAS_ARTIFACTS_ROOT:-$NAS_DATA_ROOT/artifacts}"
NAS_INCOMING_ROOT="${NAS_INCOMING_ROOT:-$NAS_DATA_ROOT/incoming}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e
  mkdir -p \
    '$NAS_LIVE_ROOT' \
    '$NAS_CURRENT_ROOT' \
    '$NAS_STAGING_ROOT' \
    '$NAS_ARCHIVE_ROOT' \
    '$NAS_CACHE_ROOT/market_heat' \
    '$NAS_CACHE_ROOT/eastmoney_sector_cache' \
    '$NAS_ARTIFACTS_ROOT/market_heat' \
    '$NAS_ARTIFACTS_ROOT/selection' \
    '$NAS_INCOMING_ROOT'

  echo 'prepared data roots:'
  for dir in \
    '$NAS_LIVE_ROOT' \
    '$NAS_CURRENT_ROOT' \
    '$NAS_STAGING_ROOT' \
    '$NAS_ARCHIVE_ROOT' \
    '$NAS_CACHE_ROOT/market_heat' \
    '$NAS_CACHE_ROOT/eastmoney_sector_cache' \
    '$NAS_ARTIFACTS_ROOT/market_heat' \
    '$NAS_ARTIFACTS_ROOT/selection' \
    '$NAS_INCOMING_ROOT'
  do
    echo \"  \$dir\"
  done
"
