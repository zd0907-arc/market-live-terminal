#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_CURRENT_ROOT="${NAS_CURRENT_ROOT:-$NAS_DATA_ROOT/research/current}"
FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-8080}"
BACKEND_BASE_URL="${BACKEND_BASE_URL:-http://127.0.0.1:${FRONTEND_HOST_PORT}}"
REFRESH_FINE_DASHBOARD="${REFRESH_FINE_DASHBOARD:-true}"
REFRESH_DAYS="${REFRESH_DAYS:-63}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e

  if [ ! -d '$NAS_CURRENT_ROOT' ]; then
    echo 'missing current release root: $NAS_CURRENT_ROOT' >&2
    exit 1
  fi

  cd '$NAS_PROJECT_ROOT'

  echo '=== current release check ==='
  bash ops/check_nas_research_release.sh '$NAS_CURRENT_ROOT'
  echo

  if [ '$REFRESH_FINE_DASHBOARD' = 'true' ]; then
    echo '=== fine dashboard refresh ==='
    curl --fail --silent --show-error \
      -X POST \
      '$BACKEND_BASE_URL/api/market_heat/fine_dashboard/refresh?days=$REFRESH_DAYS&force=true'
    echo
  fi

  echo '=== api smoke ==='
  for path in \
    '/api/health' \
    '/api/selection/health' \
    '/api/selection/daily-candidates?limit=3' \
    '/api/market_heat/latest' \
    '/api/trend-research/ideas'
  do
    echo \"-- \$path\"
    curl --fail --silent --show-error '$BACKEND_BASE_URL'\"\$path\"
    echo
  done
"
