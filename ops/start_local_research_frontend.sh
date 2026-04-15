#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/dong/Desktop/AIGC/market-live-terminal-local-research"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

cd "$ROOT"
echo "[local-research-frontend] VITE_API_PROXY_TARGET=$VITE_API_PROXY_TARGET"
echo "[local-research-frontend] FRONTEND_PORT=$FRONTEND_PORT"
npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
