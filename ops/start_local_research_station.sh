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

for key in FORMAL_MARKET_DATA_ROOT LOCAL_DATA_ROOT MARKET_DATA_ROOT LIVE_DATA_ROOT LOCAL_LIVE_DATA_ROOT DB_PATH USER_DB_PATH SELECTION_DB_PATH ATOMIC_COMPACT_DB_PATH ATOMIC_MAINBOARD_DB_PATH ATOMIC_DB_PATH ENABLE_ATOMIC_COMPACT_READ ENABLE_CLOUD_COLLECTOR ENABLE_BACKGROUND_RUNTIME SELECTION_AUTO_REFRESH_ON_READ PORT; do
  if [ -z "${!key+x}" ]; then
    load_env_value "$key"
  fi
done

is_truthy() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [ "$value" = "1" ] || [ "$value" = "true" ] || [ "$value" = "yes" ] || [ "$value" = "on" ]
}

repo_backend_pids() {
  local pids pid cwd
  pids="$(pgrep -f "backend\\.app\\.main" 2>/dev/null || true)"
  for pid in $pids; do
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    if [ "$cwd" = "$ROOT" ]; then
      echo "$pid"
    fi
  done
}

wait_for_repo_backends_exit() {
  local attempts="$1"
  local interval="$2"
  local i remaining
  i=0
  while [ "$i" -lt "$attempts" ]; do
    remaining="$(repo_backend_pids)"
    if [ -z "$remaining" ]; then
      return 0
    fi
    sleep "$interval"
    i=$((i + 1))
  done
  return 1
}

stop_repo_backends() {
  local force="${1:-false}"
  local pids pid
  pids="$(repo_backend_pids)"
  [ -n "$pids" ] || return 0
  for pid in $pids; do
    if [ "$force" = "true" ]; then
      kill -9 "$pid" 2>/dev/null || true
    else
      kill "$pid" 2>/dev/null || true
    fi
  done
}

DEFAULT_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/ZhangData/market-data}"
DEFAULT_RESEARCH_ROOT="$DEFAULT_MARKET_DATA_ROOT/research/current"
DEFAULT_LIVE_ROOT="$DEFAULT_MARKET_DATA_ROOT/live"
DEFAULT_RUNS_ROOT="$DEFAULT_MARKET_DATA_ROOT/runs"

if [ -z "${LOCAL_DATA_ROOT+x}" ] \
  && [ -z "${MARKET_DATA_ROOT+x}" ] \
  && [ -z "${LIVE_DATA_ROOT+x}" ] \
  && [ -z "${DB_PATH+x}" ] \
  && [ -z "${SELECTION_DB_PATH+x}" ] \
  && [ ! -d "$DEFAULT_MARKET_DATA_ROOT" ]; then
  echo "[local-research] 未找到 formal 数据根: $DEFAULT_MARKET_DATA_ROOT" >&2
  echo "[local-research] 请先执行: bash ops/bootstrap_mac_full_processed_sync.sh，或显式传入 LOCAL_DATA_ROOT/MARKET_DATA_ROOT/LIVE_DATA_ROOT/DB_PATH/SELECTION_DB_PATH" >&2
  exit 1
fi

if [ -d "$DEFAULT_RESEARCH_ROOT" ]; then
  DEFAULT_DATA_ROOT="$DEFAULT_RESEARCH_ROOT"
elif [ -d "$DEFAULT_MARKET_DATA_ROOT" ]; then
  DEFAULT_DATA_ROOT="$DEFAULT_MARKET_DATA_ROOT"
else
  DEFAULT_DATA_ROOT="$ROOT/data"
fi

if [ -d "$DEFAULT_LIVE_ROOT" ]; then
  DEFAULT_LIVE_DATA_ROOT="$DEFAULT_LIVE_ROOT"
elif [ -d "$DEFAULT_MARKET_DATA_ROOT" ]; then
  DEFAULT_LIVE_DATA_ROOT="$DEFAULT_MARKET_DATA_ROOT"
else
  DEFAULT_LIVE_DATA_ROOT="$ROOT/data"
fi

DATA_ROOT="${LOCAL_DATA_ROOT:-${MARKET_DATA_ROOT:-$DEFAULT_DATA_ROOT}}"
RESOLVED_LIVE_DATA_ROOT="${LOCAL_LIVE_DATA_ROOT:-${LIVE_DATA_ROOT:-$DEFAULT_LIVE_DATA_ROOT}}"
DB_PATH_DEFAULT="$RESOLVED_LIVE_DATA_ROOT/market_data.db"
USER_DB_PATH_DEFAULT="$RESOLVED_LIVE_DATA_ROOT/user_data.db"
SELECTION_DB_DEFAULT="$DATA_ROOT/selection/selection_research.db"
ATOMIC_COMPACT_DB_DEFAULT="$DATA_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db"

export DB_PATH="${DB_PATH:-$DB_PATH_DEFAULT}"
export USER_DB_PATH="${USER_DB_PATH:-$USER_DB_PATH_DEFAULT}"
export SELECTION_DB_PATH="${SELECTION_DB_PATH:-$SELECTION_DB_DEFAULT}"
export ATOMIC_COMPACT_DB_PATH="${ATOMIC_COMPACT_DB_PATH:-$ATOMIC_COMPACT_DB_DEFAULT}"
export ATOMIC_MAINBOARD_DB_PATH="${ATOMIC_MAINBOARD_DB_PATH:-$ATOMIC_COMPACT_DB_DEFAULT}"
export ATOMIC_DB_PATH="${ATOMIC_DB_PATH:-$ATOMIC_MAINBOARD_DB_PATH}"
export FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-$DEFAULT_MARKET_DATA_ROOT}"
export RESEARCH_CURRENT_ROOT="${RESEARCH_CURRENT_ROOT:-$DATA_ROOT}"
export LIVE_DATA_ROOT="${LIVE_DATA_ROOT:-$RESOLVED_LIVE_DATA_ROOT}"
export RUNS_ROOT="${RUNS_ROOT:-$DEFAULT_RUNS_ROOT}"
if [ -z "${ENABLE_ATOMIC_COMPACT_READ+x}" ]; then
  if [ -f "$ATOMIC_COMPACT_DB_PATH" ]; then
    export ENABLE_ATOMIC_COMPACT_READ="true"
  else
    export ENABLE_ATOMIC_COMPACT_READ="false"
  fi
else
  export ENABLE_ATOMIC_COMPACT_READ
fi
export ENABLE_CLOUD_COLLECTOR="${ENABLE_CLOUD_COLLECTOR:-false}"
export ENABLE_BACKGROUND_RUNTIME="${ENABLE_BACKGROUND_RUNTIME:-false}"
export SELECTION_AUTO_REFRESH_ON_READ="${SELECTION_AUTO_REFRESH_ON_READ:-false}"
export PORT="${PORT:-8001}"

COMPACT_READ_FLAG="$(printf '%s' "$ENABLE_ATOMIC_COMPACT_READ" | tr '[:upper:]' '[:lower:]')"
COMPACT_READ_ENABLED=false
if [ "$COMPACT_READ_FLAG" = "1" ] || [ "$COMPACT_READ_FLAG" = "true" ] || [ "$COMPACT_READ_FLAG" = "yes" ] || [ "$COMPACT_READ_FLAG" = "on" ]; then
  COMPACT_READ_ENABLED=true
fi

if [ ! -f "$DB_PATH" ]; then
  echo "[local-research] 未找到 market DB: $DB_PATH" >&2
  echo "[local-research] 请先执行: bash ops/bootstrap_mac_full_processed_sync.sh" >&2
  exit 1
fi

if [ ! -f "$SELECTION_DB_PATH" ]; then
  echo "[local-research] 未找到 selection DB: $SELECTION_DB_PATH" >&2
  echo "[local-research] 请先执行: bash ops/bootstrap_mac_full_processed_sync.sh" >&2
  exit 1
fi

if [ "$COMPACT_READ_ENABLED" = "true" ]; then
  if [ -z "$ATOMIC_COMPACT_DB_PATH" ]; then
    echo "[local-research] ENABLE_ATOMIC_COMPACT_READ 已开启，但 ATOMIC_COMPACT_DB_PATH 为空" >&2
    exit 1
  fi
  if [ ! -f "$ATOMIC_COMPACT_DB_PATH" ]; then
    echo "[local-research] 未找到 compact atomic DB: $ATOMIC_COMPACT_DB_PATH" >&2
    exit 1
  fi
  export ATOMIC_MAINBOARD_DB_PATH="$ATOMIC_COMPACT_DB_PATH"
  export ATOMIC_DB_PATH="$ATOMIC_COMPACT_DB_PATH"
elif [ ! -f "$ATOMIC_MAINBOARD_DB_PATH" ]; then
  echo "[local-research] 未找到本地 atomic DB: $ATOMIC_MAINBOARD_DB_PATH" >&2
  echo "[local-research] 将以 live/selection/market_heat 轻量模式启动；需要 atomic/5m 大库的接口需走 NAS 派生库或后续查询接口。" >&2
  export ATOMIC_COMPACT_DB_PATH=""
  export ATOMIC_MAINBOARD_DB_PATH=""
  export ATOMIC_DB_PATH=""
fi

mkdir -p "$DATA_ROOT" "$RESOLVED_LIVE_DATA_ROOT" "$(dirname "$SELECTION_DB_PATH")" "$(dirname "$ATOMIC_MAINBOARD_DB_PATH")" "$(dirname "$DB_PATH")" "$(dirname "$USER_DB_PATH")"

EXISTING_BACKEND_PIDS="$(repo_backend_pids)"
if [ -n "$EXISTING_BACKEND_PIDS" ]; then
  echo "[local-research] 检测到同仓库已有后端实例: $(printf '%s' "$EXISTING_BACKEND_PIDS" | tr '\n' ' ')" >&2
  if is_truthy "$RESTART_IF_RUNNING"; then
    echo "[local-research] 将先停止旧实例，再启动新实例。" >&2
    stop_repo_backends false
    if ! wait_for_repo_backends_exit 10 0.5; then
      echo "[local-research] 旧实例未在预期时间内退出，执行强制停止。" >&2
      stop_repo_backends true
      if ! wait_for_repo_backends_exit 6 0.5; then
        echo "[local-research] 无法清理旧实例，请先手工检查 backend.app.main 进程。" >&2
        exit 1
      fi
    fi
  else
    echo "[local-research] 已拒绝重复启动。若要自动重启，请显式设置 RESTART_IF_RUNNING=true。" >&2
    exit 1
  fi
fi

PORT_CONFLICT_PIDS="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PORT_CONFLICT_PIDS" ]; then
  echo "[local-research] 端口 $PORT 已被其他进程占用，拒绝继续启动：" >&2
  for pid in $PORT_CONFLICT_PIDS; do
    ps -p "$pid" -o pid=,command= >&2 || true
  done
  exit 1
fi

cd "$ROOT"
echo "[local-research] DB_PATH=$DB_PATH"
echo "[local-research] USER_DB_PATH=$USER_DB_PATH"
echo "[local-research] SELECTION_DB_PATH=$SELECTION_DB_PATH"
echo "[local-research] ATOMIC_MAINBOARD_DB_PATH=$ATOMIC_MAINBOARD_DB_PATH"
echo "[local-research] ATOMIC_DB_PATH=$ATOMIC_DB_PATH"
echo "[local-research] ENABLE_ATOMIC_COMPACT_READ=$ENABLE_ATOMIC_COMPACT_READ"
if [ -n "$ATOMIC_COMPACT_DB_PATH" ]; then
  echo "[local-research] ATOMIC_COMPACT_DB_PATH=$ATOMIC_COMPACT_DB_PATH"
fi
echo "[local-research] ENABLE_BACKGROUND_RUNTIME=$ENABLE_BACKGROUND_RUNTIME"
echo "[local-research] PORT=$PORT"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in "$ROOT/.venv/bin/python" "/usr/bin/python3" "python3" "/Users/dong/.browser-use-env/bin/python3"; do
    if [ "$candidate" = "python3" ]; then
      if python3 -c "import fastapi" >/dev/null 2>&1; then
        PYTHON_BIN="python3"
        break
      fi
    elif [ -x "$candidate" ] && "$candidate" -c "import fastapi" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
exec "$PYTHON_BIN" -m backend.app.main
