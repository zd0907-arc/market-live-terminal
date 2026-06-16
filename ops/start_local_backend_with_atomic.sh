#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH_DEFAULT="$ROOT/data/market_data.db"
USER_DB_PATH_DEFAULT="$ROOT/data/user_data.db"
FORMAL_DATA_ROOT_DEFAULT="/Users/dong/ZhangData/market-data"
ATOMIC_DEFAULT="${ATOMIC_DEFAULT:-$FORMAL_DATA_ROOT_DEFAULT/atomic_facts/market_atomic_mainboard_compact_current.db}"
ATOMIC_REPO_DEFAULT="$ROOT/data/atomic_facts/market_atomic_mainboard_compact_current.db"

export DB_PATH="${DB_PATH:-$DB_PATH_DEFAULT}"
export USER_DB_PATH="${USER_DB_PATH:-$USER_DB_PATH_DEFAULT}"
if [ -n "${ATOMIC_MAINBOARD_DB_PATH:-}" ]; then
  RESOLVED_ATOMIC="$ATOMIC_MAINBOARD_DB_PATH"
elif [ -n "${1:-}" ]; then
  RESOLVED_ATOMIC="$1"
elif [ -f "$ATOMIC_DEFAULT" ]; then
  RESOLVED_ATOMIC="$ATOMIC_DEFAULT"
elif [ -f "$ATOMIC_REPO_DEFAULT" ]; then
  RESOLVED_ATOMIC="$ATOMIC_REPO_DEFAULT"
else
  RESOLVED_ATOMIC="$ATOMIC_REPO_DEFAULT"
fi

export ATOMIC_MAINBOARD_DB_PATH="$RESOLVED_ATOMIC"
export ATOMIC_DB_PATH="${ATOMIC_DB_PATH:-$ATOMIC_MAINBOARD_DB_PATH}"

if [ ! -f "$ATOMIC_DB_PATH" ]; then
  echo "[atomic-backend] 未找到 atomic DB: $ATOMIC_DB_PATH" >&2
  echo "[atomic-backend] 兼容脚本默认优先读 compact_current；也可显式传入任意 atomic db 绝对路径" >&2
  exit 1
fi

cd "$ROOT"

echo "[atomic-backend] DB_PATH=$DB_PATH"
echo "[atomic-backend] USER_DB_PATH=$USER_DB_PATH"
echo "[atomic-backend] ATOMIC_DB_PATH=$ATOMIC_DB_PATH"
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
