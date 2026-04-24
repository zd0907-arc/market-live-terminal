#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_python_bin() {
  local candidate
  for candidate in \
    "$ROOT_DIR/.venv/bin/python" \
    "python3" \
    "/usr/bin/python3" \
    "/Users/dong/.browser-use-env/bin/python3"
  do
    if [ "$candidate" = "python3" ]; then
      if command -v python3 >/dev/null 2>&1 && python3 -c "import pytest" >/dev/null 2>&1; then
        echo "python3"
        return 0
      fi
    elif [ -x "$candidate" ] && "$candidate" -c "import pytest" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON_BIN="$(resolve_python_bin)"; then
  echo "ERROR: 未找到可运行 pytest 的 Python 环境。" >&2
  echo "建议先执行：" >&2
  echo "  cd $ROOT_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt" >&2
  exit 1
fi

echo "==> Version consistency"
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_version_consistency.py"

echo
echo "==> Backend tests"
"$PYTHON_BIN" -m pytest "$ROOT_DIR/backend/tests" -q

echo
echo "==> Frontend build"
npm --prefix "$ROOT_DIR" run build
