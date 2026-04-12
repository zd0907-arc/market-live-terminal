#!/bin/zsh
set -euo pipefail
ssh -o StrictHostKeyChecking=no laqiyuan@100.115.228.56 "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\laqiyuan\start_atomic_backfill_job.ps1 -ConfigPath D:\market-live-terminal\backend\scripts\configs\atomic_backfill_windows.full_reverse_202604_to_202501.json -Tag atomic_backfill_full_reverse"
