@echo off
:: =========================================================
:: ZhangData - Windows Live Crawler Auto-Starter
:: This script is meant to be run by Windows Task Scheduler
:: =========================================================

echo [ZhangData] Starting Live Market Crawler...
echo [Cloud Node] Targeting 111.229.144.202
echo.

:: Modify the path below if your python environment or project lives elsewhere
cd /d "D:\market-live-terminal"

:: Set environment variables required for Cloud Ingestion
set CLOUD_API_URL=http://111.229.144.202:8000

if "%INGEST_TOKEN%"=="" (
    echo [ERROR] INGEST_TOKEN is not set. Please configure it in system environment variables.
    exit /b 1
)

:: Run the crawler. It will safely idle if outside trading hours.
:: To keep the window open for debugging, remove the 'pythonw' and use 'python'
python backend\scripts\live_crawler_win.py

pause
