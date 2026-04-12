@echo off
setlocal

set PY=C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe
set ROOT=D:\market-live-terminal
set SCRIPT=%ROOT%\backend\scripts\run_atomic_backfill_windows.py
set DEFAULT_CONFIG=%ROOT%\backend\scripts\configs\atomic_backfill_windows.sample.json
set LOG_DIR=%ROOT%\.run
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=%DEFAULT_CONFIG%

set TS=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TS=%TS: =0%
set LOG_FILE=%LOG_DIR%\atomic_backfill_%TS%.log

echo [atomic-backfill] ROOT=%ROOT%
echo [atomic-backfill] CONFIG=%CONFIG%
echo [atomic-backfill] LOG=%LOG_FILE%

"%PY%" -u "%SCRIPT%" --config "%CONFIG%" >> "%LOG_FILE%" 2>&1
set RC=%ERRORLEVEL%

echo [atomic-backfill] rc=%RC%
echo [atomic-backfill] log=%LOG_FILE%
exit /b %RC%
