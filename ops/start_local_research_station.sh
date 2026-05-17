#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_MARKET_DATA_ROOT="/Users/dong/Desktop/AIGC/market-data"
if [ -d "$DEFAULT_MARKET_DATA_ROOT" ]; then
  DEFAULT_DATA_ROOT="$DEFAULT_MARKET_DATA_ROOT"
else
  DEFAULT_DATA_ROOT="$ROOT/data"
fi
DATA_ROOT="${LOCAL_DATA_ROOT:-${MARKET_DATA_ROOT:-$DEFAULT_DATA_ROOT}}"
DB_PATH_DEFAULT="$DATA_ROOT/market_data.db"
USER_DB_PATH_DEFAULT="$DATA_ROOT/user_data.db"
SELECTION_DB_DEFAULT="$DATA_ROOT/selection/selection_research.db"
ATOMIC_DB_DEFAULT="$DATA_ROOT/atomic_facts/market_atomic_mainboard_full_reverse.db"
ATOMIC_COMPACT_DB_DEFAULT="$DATA_ROOT/atomic_facts/shadow/market_atomic_mainboard_compact_current.db"

export DB_PATH="${DB_PATH:-$DB_PATH_DEFAULT}"
export USER_DB_PATH="${USER_DB_PATH:-$USER_DB_PATH_DEFAULT}"
export SELECTION_DB_PATH="${SELECTION_DB_PATH:-$SELECTION_DB_DEFAULT}"
export ATOMIC_MAINBOARD_DB_PATH="${ATOMIC_MAINBOARD_DB_PATH:-$ATOMIC_DB_DEFAULT}"
export ATOMIC_DB_PATH="${ATOMIC_DB_PATH:-$ATOMIC_DB_DEFAULT}"
export ATOMIC_COMPACT_DB_PATH="${ATOMIC_COMPACT_DB_PATH:-$ATOMIC_COMPACT_DB_DEFAULT}"
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
  echo "[local-research] 未找到 atomic DB: $ATOMIC_MAINBOARD_DB_PATH" >&2
  echo "[local-research] 请先执行: bash ops/bootstrap_mac_full_processed_sync.sh" >&2
  exit 1
fi

mkdir -p "$DATA_ROOT" "$(dirname "$SELECTION_DB_PATH")" "$(dirname "$ATOMIC_MAINBOARD_DB_PATH")"

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
"$PYTHON_BIN" -m backend.app.main
