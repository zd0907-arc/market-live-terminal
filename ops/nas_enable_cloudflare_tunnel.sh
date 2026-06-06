#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"
NAS_CLOUDFLARE_DIR="${NAS_CLOUDFLARE_DIR:-/volume1/docker/market-live-terminal/cloudflared}"
TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"

if [ -z "$TUNNEL_TOKEN" ]; then
  echo "missing CLOUDFLARE_TUNNEL_TOKEN" >&2
  exit 1
fi

ssh -o ConnectTimeout=8 "$NAS_HOST" "mkdir -p '$NAS_PROJECT_ROOT/deploy' '$NAS_CLOUDFLARE_DIR'"

cat "$ROOT_DIR/deploy/docker-compose.cloudflare-tunnel.yml" \
  | ssh "$NAS_HOST" "cat > '$NAS_PROJECT_ROOT/deploy/docker-compose.cloudflare-tunnel.yml'"

ssh "$NAS_HOST" "cat > '$NAS_CLOUDFLARE_DIR/.env' <<EOF
TUNNEL_TOKEN=$TUNNEL_TOKEN
EOF
chmod 600 '$NAS_CLOUDFLARE_DIR/.env'"

ssh "$NAS_HOST" \
  "cd '$NAS_PROJECT_ROOT' \
   && docker compose --env-file '$NAS_CLOUDFLARE_DIR/.env' -f deploy/docker-compose.cloudflare-tunnel.yml up -d"

ssh "$NAS_HOST" \
  "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep cloudflared-nas || true"

echo "NAS_HOST=$NAS_HOST"
echo "NAS_PROJECT_ROOT=$NAS_PROJECT_ROOT"
echo "NAS_CLOUDFLARE_DIR=$NAS_CLOUDFLARE_DIR"
echo "cloudflared compose started"
