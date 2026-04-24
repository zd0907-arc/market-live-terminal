#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH_DEFAULT="$ROOT/data/market_data.db"
USER_DB_PATH_DEFAULT="$ROOT/data/user_data.db"
ATOMIC_DEFAULT="$ROOT/data/atomic_facts/market_atomic_mainboard_full_reverse.db"

export DB_PATH="${DB_PATH:-$DB_PATH_DEFAULT}"
export USER_DB_PATH="${USER_DB_PATH:-$USER_DB_PATH_DEFAULT}"
export ATOMIC_MAINBOARD_DB_PATH="${ATOMIC_MAINBOARD_DB_PATH:-${1:-$ATOMIC_DEFAULT}}"
export ATOMIC_DB_PATH="${ATOMIC_DB_PATH:-$ATOMIC_MAINBOARD_DB_PATH}"

if [ ! -f "$ATOMIC_DB_PATH" ]; then
  echo "[atomic-backend] 未找到 atomic DB: $ATOMIC_DB_PATH" >&2
  echo "[atomic-backend] 可这样启动: bash ops/start_local_backend_with_atomic.sh /绝对路径/market_atomic_mainboard_full_reverse.db" >&2
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
