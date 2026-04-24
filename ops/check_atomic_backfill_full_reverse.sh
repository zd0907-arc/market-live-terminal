#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/ops/check_atomic_backfill_status_brief.sh" atomic_backfill_windows.full_reverse_202604_to_202501.json
