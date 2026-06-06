#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"
NAS_ENV_FILE="${NAS_ENV_FILE:-$NAS_PROJECT_ROOT/.env.nas-full}"
NAS_COMPOSE_FILE="${NAS_COMPOSE_FILE:-deploy/docker-compose.nas-full.yml}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e
  cd '$NAS_PROJECT_ROOT'
  echo '=== compose ps ==='
  docker compose --env-file '$NAS_ENV_FILE' -f '$NAS_COMPOSE_FILE' --profile crawler ps
  echo
  echo '=== crawler logs tail ==='
  docker logs --tail 120 market-crawler-nas 2>&1 || true
  echo
  echo '=== backend logs tail ==='
  docker logs --tail 120 market-backend-nas 2>&1 || true
"
