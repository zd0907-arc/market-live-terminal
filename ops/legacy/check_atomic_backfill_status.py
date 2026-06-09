#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys

HOST = 'laqiyuan@100.115.228.56'
DEFAULT_CONFIG = 'atomic_backfill_windows.stage_1_202604.json'


def build_ps(config_file: str) -> str:
    win_config_path = f"D:\\market-live-terminal\\backend\\scripts\\configs\\{config_file}"
    return rf'''
$ErrorActionPreference = 'Stop'
$configPath = '{win_config_path}'
if (!(Test-Path $configPath)) {{ throw 'config not found: ' + $configPath }}
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$statePath = $config.state_file
$reportPath = $config.report_file
$atomicDb = $config.atomic_db
$runDir = 'D:\market-live-terminal\.run'
$configBase = [System.IO.Path]::GetFileName($configPath)
$state = $null
$report = $null
if (Test-Path $statePath) {{ $state = Get-Content $statePath -Raw | ConvertFrom-Json }}
if (Test-Path $reportPath) {{ $report = Get-Content $reportPath -Raw | ConvertFrom-Json }}
$logPrefix = [System.IO.Path]::GetFileNameWithoutExtension([System.IO.Path]::GetFileName($statePath)) -replace '_state$',''
$latestLog = Get-ChildItem $runDir -File | Where-Object {{ $_.Name -like ($logPrefix + '*.log') -and $_.Name -notlike '*.err.log' }} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$latestErr = Get-ChildItem $runDir -File | Where-Object {{ $_.Name -like ($logPrefix + '*.err.log') }} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$pyProc = Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_atomic_backfill_windows.py*' -and $_.CommandLine -like ('*' + $configBase + '*') }} | Select-Object -First 1
$procInfo = $null
if ($pyProc) {{
  try {{
    $p = Get-Process -Id $pyProc.ProcessId -ErrorAction Stop
    $procInfo = [pscustomobject]@{{
      pid = $p.Id
      cpu = $p.CPU
      start_time = $p.StartTime.ToString('yyyy-MM-dd HH:mm:ss')
    }}
  }} catch {{}}
}}
$seven = Get-Process 7z -ErrorAction SilentlyContinue | Select-Object -First 1
$sevenInfo = $null
if ($seven) {{
  $sevenInfo = [pscustomobject]@{{
    pid = $seven.Id
    cpu = $seven.CPU
    start_time = $seven.StartTime.ToString('yyyy-MM-dd HH:mm:ss')
  }}
}}
$dbStats = $null
if (Test-Path $atomicDb) {{
  try {{
    $py = 'C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe'
    $dbStatsJson = & $py -c "import json,sqlite3,sys; conn=sqlite3.connect(sys.argv[1]); cur=conn.cursor(); stats={{'trade_daily':cur.execute('select count(*) from atomic_trade_daily').fetchone()[0],'order_daily':cur.execute('select count(*) from atomic_order_daily').fetchone()[0],'book_daily':cur.execute('select count(*) from atomic_book_state_daily').fetchone()[0],'trade_5m':cur.execute('select count(*) from atomic_trade_5m').fetchone()[0],'limit_daily':cur.execute('select count(*) from atomic_limit_state_daily').fetchone()[0]}}; print(json.dumps(stats, ensure_ascii=False))" $atomicDb
    if ($dbStatsJson) {{ $dbStats = $dbStatsJson | ConvertFrom-Json }}
  }} catch {{}}
}}
$lastCompleted = $null
if ($state -and $state.completed_days.Count -gt 0) {{ $lastCompleted = $state.completed_days[-1] }}
$tail = $null
if ($latestLog) {{
  $tailLines = [string[]](Get-Content $latestLog.FullName -Tail 5)
  $tail = $tailLines -join "`n"
}}
[pscustomobject]@{{
  config = $configBase
  status = if ($state) {{ $state.status }} else {{ 'no_state' }}
  started_at = if ($state) {{ $state.started_at }} else {{ $null }}
  finished_at = if ($state) {{ $state.finished_at }} else {{ $null }}
  completed_days = if ($state) {{ $state.completed_days.Count }} else {{ 0 }}
  failed_days = if ($state) {{ $state.failed_days.Count }} else {{ 0 }}
  last_completed_day = $lastCompleted
  running_python = $procInfo
  running_7z = $sevenInfo
  atomic_db = $atomicDb
  db_stats = $dbStats
  report_completed_days = if ($report) {{ $report.completed_day_count }} else {{ $null }}
  latest_log = if ($latestLog) {{ [pscustomobject]@{{ path = $latestLog.FullName; size = $latestLog.Length; last_write = $latestLog.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss') }} }} else {{ $null }}
  latest_err = if ($latestErr) {{ [pscustomobject]@{{ path = $latestErr.FullName; size = $latestErr.Length; last_write = $latestErr.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss') }} }} else {{ $null }}
  log_tail = $tail
}} | ConvertTo-Json -Depth 6
'''


def main() -> int:
    config = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG
    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', HOST, 'powershell', '-NoProfile', '-Command', '-']
    result = subprocess.run(cmd, input=build_ps(config), text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    print(result.stdout.strip())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
