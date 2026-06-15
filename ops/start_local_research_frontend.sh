#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESTART_IF_RUNNING="${RESTART_IF_RUNNING:-true}"

load_env_value() {
  local key="$1"
  local env_file="$ROOT/.env.local"
  local line value
  [ -f "$env_file" ] || return 0
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$env_file" | tail -n 1 || true)"
  [ -n "$line" ] || return 0
  value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  export "$key=$value"
}

for key in FRONTEND_PORT BACKEND_PORT VITE_API_PROXY_TARGET; do
  if [ -z "${!key+x}" ]; then
    load_env_value "$key"
  fi
done

FRONTEND_PORT="${FRONTEND_PORT:-3001}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
VITE_BIN="${VITE_BIN:-$ROOT/node_modules/.bin/vite}"

is_truthy() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [ "$value" = "1" ] || [ "$value" = "true" ] || [ "$value" = "yes" ] || [ "$value" = "on" ]
}

repo_frontend_pids() {
  local pids pid cwd
  pids="$(pgrep -f 'node_modules/.bin/vite' 2>/dev/null || true)"
  for pid in $pids; do
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    if [ "$cwd" = "$ROOT" ]; then
      echo "$pid"
    fi
  done
}

wait_for_repo_frontends_exit() {
  local attempts="$1"
  local interval="$2"
  local i remaining
  i=0
  while [ "$i" -lt "$attempts" ]; do
    remaining="$(repo_frontend_pids)"
    if [ -z "$remaining" ]; then
      return 0
    fi
    sleep "$interval"
    i=$((i + 1))
  done
  return 1
}

stop_repo_frontends() {
  local force="${1:-false}"
  local pids pid
  pids="$(repo_frontend_pids)"
  [ -n "$pids" ] || return 0
  for pid in $pids; do
    if [ "$force" = "true" ]; then
      kill -9 "$pid" 2>/dev/null || true
    else
      kill "$pid" 2>/dev/null || true
    fi
  done
}

if [ ! -x "$VITE_BIN" ]; then
  echo "[local-research-frontend] 未找到 Vite 可执行文件: $VITE_BIN" >&2
  echo "[local-research-frontend] 请先在仓库根目录执行: npm install" >&2
  exit 1
fi

EXISTING_FRONTEND_PIDS="$(repo_frontend_pids)"
if [ -n "$EXISTING_FRONTEND_PIDS" ]; then
  echo "[local-research-frontend] 检测到同仓库已有前端实例: $(printf '%s' "$EXISTING_FRONTEND_PIDS" | tr '\n' ' ')" >&2
  if is_truthy "$RESTART_IF_RUNNING"; then
    echo "[local-research-frontend] 将先停止旧实例，再启动新实例。" >&2
    stop_repo_frontends false
    if ! wait_for_repo_frontends_exit 10 0.5; then
      echo "[local-research-frontend] 旧实例未在预期时间内退出，执行强制停止。" >&2
      stop_repo_frontends true
      if ! wait_for_repo_frontends_exit 6 0.5; then
        echo "[local-research-frontend] 无法清理旧实例，请先手工检查 vite 进程。" >&2
        exit 1
      fi
    fi
  else
    echo "[local-research-frontend] 已拒绝重复启动。若要自动重启，请显式设置 RESTART_IF_RUNNING=true。" >&2
    exit 1
  fi
fi

PORT_CONFLICT_PIDS="$(lsof -tiTCP:"$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PORT_CONFLICT_PIDS" ]; then
  echo "[local-research-frontend] 端口 $FRONTEND_PORT 已被其他进程占用，拒绝继续启动：" >&2
  for pid in $PORT_CONFLICT_PIDS; do
    ps -p "$pid" -o pid=,command= >&2 || true
  done
  exit 1
fi

cd "$ROOT"
echo "[local-research-frontend] VITE_API_PROXY_TARGET=$VITE_API_PROXY_TARGET"
echo "[local-research-frontend] FRONTEND_PORT=$FRONTEND_PORT"
exec "$VITE_BIN" --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
