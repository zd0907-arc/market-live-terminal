@echo off
setlocal EnableExtensions

:: =========================================================
:: ZhangData - Windows Live Crawler Auto-Starter
:: Stable entry for Task Scheduler / watchdog / manual recovery
:: 历史环境变量名仍叫 CLOUD_API_URL，但当前正式默认 ingest 目标应理解为 NAS 在线后端。
:: =========================================================

set "PROJECT_ROOT=D:\market-live-terminal"
set "DEFAULT_PYTHON_EXE=C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe"
set "LOG_DIR=%PROJECT_ROOT%\.run"
set "LOG_FILE=%LOG_DIR%\live_crawler.log"

if not exist "%PROJECT_ROOT%" exit /b 2
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if "%PYTHON_EXE%"=="" set "PYTHON_EXE=%DEFAULT_PYTHON_EXE%"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "INGEST_TOKEN="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('INGEST_TOKEN','Machine')"`) do set "INGEST_TOKEN=%%i"

set "CLOUD_API_URL="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('CLOUD_API_URL','Machine')"`) do set "CLOUD_API_URL=%%i"
if "%CLOUD_API_URL%"=="" set "CLOUD_API_URL=http://dxp4800pro:8080"

set "FOCUS_TICK_INTERVAL_SECONDS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('FOCUS_TICK_INTERVAL_SECONDS','Machine')"`) do set "FOCUS_TICK_INTERVAL_SECONDS=%%i"
set "WARM_TICK_INTERVAL_SECONDS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('WARM_TICK_INTERVAL_SECONDS','Machine')"`) do set "WARM_TICK_INTERVAL_SECONDS=%%i"
set "FULL_SWEEP_INTERVAL_SECONDS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('FULL_SWEEP_INTERVAL_SECONDS','Machine')"`) do set "FULL_SWEEP_INTERVAL_SECONDS=%%i"
set "AKSHARE_TICK_TIMEOUT_SECONDS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('AKSHARE_TICK_TIMEOUT_SECONDS','Machine')"`) do set "AKSHARE_TICK_TIMEOUT_SECONDS=%%i"

if "%INGEST_TOKEN%"=="" (
  echo [%date% %time%] [BOOT] ERROR: INGEST_TOKEN is not set.>> "%LOG_FILE%"
  exit /b 1
)

echo [%date% %time%] [BOOT] Starting live crawler with PYTHON_EXE=%PYTHON_EXE% CLOUD_API_URL=%CLOUD_API_URL%>> "%LOG_FILE%"
cd /d "%PROJECT_ROOT%"
"%PYTHON_EXE%" -u backend\scripts\live_crawler_win.py >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] [BOOT] live crawler exited code=%EXIT_CODE%>> "%LOG_FILE%"
exit /b %EXIT_CODE%
