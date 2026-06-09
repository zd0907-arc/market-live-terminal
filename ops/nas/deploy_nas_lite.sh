#!/usr/bin/env bash
set -euo pipefail

# 兼容说明（2026-06-08）：
# 这是 NAS lite 的旧 flat-data 兼容链。
# 它不再从 repo data/*.db 取源，而是显式从正式 live/ 轻量库复制，
# 避免删掉 repo fallback 后再次把兼容副本当成正式真相。

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
export COPYFILE_DISABLE=1

NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_FRONTEND_PORT="${NAS_FRONTEND_PORT:-8080}"
NAS_ENV_FILE="${NAS_ENV_FILE:-$NAS_PROJECT_ROOT/.env.nas-lite}"
NAS_BASE_IMAGE_PREFIX="${NAS_BASE_IMAGE_PREFIX:-docker.m.daocloud.io/library/}"
WINDOWS_HOST="${WINDOWS_HOST:-laqiyuan@100.115.228.56}"
FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/Desktop/AIGC/market-data}"
LIVE_DATA_ROOT="${LIVE_DATA_ROOT:-$FORMAL_MARKET_DATA_ROOT/live}"
LOCAL_USER_DB="${LOCAL_USER_DB:-$LIVE_DATA_ROOT/user_data.db}"
LOCAL_MARKET_DB="${LOCAL_MARKET_DB:-$LIVE_DATA_ROOT/market_data.db}"

rand_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return
  fi
  LC_ALL=C dd if=/dev/urandom bs=64 count=1 2>/dev/null | base64 | tr -dc 'A-Za-z0-9' | cut -c1-48
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh
require_cmd tar

if [ ! -f "$LOCAL_USER_DB" ] || [ ! -f "$LOCAL_MARKET_DB" ]; then
  echo "formal live DB missing: LOCAL_USER_DB=$LOCAL_USER_DB LOCAL_MARKET_DB=$LOCAL_MARKET_DB" >&2
  exit 1
fi

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$NAS_HOST" 'echo ok' >/dev/null 2>&1; then
  echo "NAS SSH unavailable: $NAS_HOST" >&2
  exit 1
fi

INGEST_TOKEN="$(
  ssh "$WINDOWS_HOST" \
    "powershell -NoProfile -Command \"[Environment]::GetEnvironmentVariable('INGEST_TOKEN','Machine')\"" \
    | tr -d '\r' \
    | tail -n 1
)"

if [ -z "$INGEST_TOKEN" ]; then
  echo "failed to load INGEST_TOKEN from Windows host" >&2
  exit 1
fi

WRITE_API_TOKEN="${WRITE_API_TOKEN:-$(rand_token)}"
mkdir -p "$ROOT_DIR/.run"
printf '%s\n' "$WRITE_API_TOKEN" > "$ROOT_DIR/.run/nas_write_api_token.txt"
chmod 600 "$ROOT_DIR/.run/nas_write_api_token.txt"

ssh "$NAS_HOST" "mkdir -p '$NAS_PROJECT_ROOT' '$NAS_DATA_ROOT' && find '$NAS_PROJECT_ROOT' -mindepth 1 -maxdepth 1 -exec rm -rf {} +"

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.run' \
  --exclude='dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='._*' \
  --exclude='.DS_Store' \
  --exclude='.obsidian' \
  --exclude='.pytest_cache' \
  --exclude='logs' \
  --exclude='.env.local' \
  --exclude='backend/app/db/*.db' \
  --exclude='data/market_data.db' \
  --exclude='data/user_data.db' \
  --exclude='market_data.db' \
  --exclude='market_data_history.db' \
  -C "$ROOT_DIR" \
  -czf - . \
  | ssh "$NAS_HOST" "cd '$NAS_PROJECT_ROOT' && tar -xzf -"

cat "$LOCAL_USER_DB" | ssh "$NAS_HOST" "cat > '$NAS_DATA_ROOT/user_data.db'"
cat "$LOCAL_MARKET_DB" | ssh "$NAS_HOST" "cat > '$NAS_DATA_ROOT/market_data.db'"

ssh "$NAS_HOST" "cat > '$NAS_ENV_FILE' <<EOF
MARKET_DATA_HOST_DIR=$NAS_DATA_ROOT
FRONTEND_HOST_PORT=$NAS_FRONTEND_PORT
BASE_IMAGE_PREFIX=$NAS_BASE_IMAGE_PREFIX
INGEST_TOKEN=$INGEST_TOKEN
WRITE_API_TOKEN=$WRITE_API_TOKEN
ENABLE_BACKGROUND_RUNTIME=false
ENABLE_CLOUD_COLLECTOR=false
ENABLE_RESEARCH_API_ROUTES=false
VITE_CLOUD_LITE_MODE=true
TZ=Asia/Shanghai
EOF"

ssh "$NAS_HOST" "cd '$NAS_PROJECT_ROOT' && docker compose --env-file '$NAS_ENV_FILE' -f deploy/docker-compose.nas-lite.yml up -d --build"

echo "NAS_HOST=$NAS_HOST"
echo "NAS_PROJECT_ROOT=$NAS_PROJECT_ROOT"
echo "NAS_DATA_ROOT=$NAS_DATA_ROOT"
echo "LOCAL_USER_DB=$LOCAL_USER_DB"
echo "LOCAL_MARKET_DB=$LOCAL_MARKET_DB"
echo "FRONTEND_URL=http://192.168.3.43:$NAS_FRONTEND_PORT"
