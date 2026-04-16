#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export L2_WIN_HOST="${L2_WIN_HOST:-}"
export L2_WIN_HOST_CANDIDATES="${L2_WIN_HOST_CANDIDATES:-laqiyuan@192.168.3.108,laqiyuan@100.115.228.56}"

python3 backend/scripts/run_postclose_l2_daily.py \
  --bootstrap-mac-full-sync \
  --bootstrap-only \
  "$@"
