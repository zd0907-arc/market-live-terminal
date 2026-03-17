#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Version consistency"
python3 "$ROOT_DIR/scripts/check_version_consistency.py"

echo
echo "==> Backend tests"
python3 -m pytest "$ROOT_DIR/backend/tests" -q

echo
echo "==> Frontend build"
npm --prefix "$ROOT_DIR" run build
