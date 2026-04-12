#!/bin/zsh
set -euo pipefail
ssh -o StrictHostKeyChecking=no laqiyuan@100.115.228.56 'cmd /c "set ROOT=D:\\market-live-terminal && set PY=C:\\Users\\laqiyuan\\AppData\\Local\\Programs\\Python\\Python311\\python.exe && set SCRIPT=D:\\market-live-terminal\\backend\\scripts\\run_atomic_backfill_windows.py && set CFG=D:\\market-live-terminal\\backend\\scripts\\configs\\atomic_backfill_windows.full_reverse_202604_to_202501.json && set LOG=D:\\market-live-terminal\\.run\\atomic_backfill_full_reverse_direct.log && start "" /b cmd /c ""%PY%" -u "%SCRIPT%" --config "%CFG%" >> "%LOG%" 2>&1""'
