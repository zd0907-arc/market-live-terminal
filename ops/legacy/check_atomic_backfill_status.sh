#!/bin/zsh
set -euo pipefail
HOST="laqiyuan@100.115.228.56"
CONFIG_FILE="${1:-atomic_backfill_windows.stage_1_202604.json}"
ssh -o StrictHostKeyChecking=no "$HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\laqiyuan\\get_atomic_backfill_status.ps1 -ConfigFile $CONFIG_FILE"
