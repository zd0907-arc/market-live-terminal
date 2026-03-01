@echo off
echo ===== ETL V3 Autonomous Runner (with Auto-Retry) =====
echo Started: %date% %time%
echo Started: %date% %time% >> D:\market-live-terminal\etl_output.log

:: Delete stale PID lock if exists
if exist D:\market-live-terminal\.etl.lock (
    echo [*] Removing stale PID lock...
    del D:\market-live-terminal\.etl.lock
)

:: Run ETL in a retry loop (up to 20 attempts)
set ATTEMPT=0
:RETRY
set /a ATTEMPT+=1
echo.
echo ===== Attempt %ATTEMPT% at %date% %time% =====
echo ===== Attempt %ATTEMPT% at %date% %time% ===== >> D:\market-live-terminal\etl_output.log

python D:\market-live-terminal\backend\scripts\etl_worker_win.py ^
    D:\MarketData ^
    D:\market-live-terminal\market_data_history.db ^
    --workers 4 ^
    >> D:\market-live-terminal\etl_output.log 2>&1

:: Check if ETL exited cleanly (exit code 0 = all done)
if %ERRORLEVEL% EQU 0 (
    echo [+] ETL completed successfully at %date% %time%
    echo [+] ETL completed successfully at %date% %time% >> D:\market-live-terminal\etl_output.log
    goto DONE
)

:: Crash detected - clean up and retry
echo [!] ETL crashed with code %ERRORLEVEL% at %date% %time%. Retrying in 30s...
echo [!] ETL crashed with code %ERRORLEVEL% at %date% %time%. Retrying in 30s... >> D:\market-live-terminal\etl_output.log
if exist D:\market-live-terminal\.etl.lock del D:\market-live-terminal\.etl.lock
timeout /t 30 /nobreak >nul

if %ATTEMPT% LSS 20 goto RETRY

echo [!] Max retries (20) reached. Giving up.

:DONE
echo ===== ETL Runner finished at %date% %time% =====
echo ===== ETL Runner finished at %date% %time% ===== >> D:\market-live-terminal\etl_output.log
