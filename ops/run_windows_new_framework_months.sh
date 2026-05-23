#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ "$#" -eq 0 ]; then
  set -- --start-month 2026-03 --end-month 2026-01 --background
fi

python3 backend/scripts/run_windows_new_framework_months.py "$@"
