#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
import json

from backend.scripts.run_daily_new_framework import (
    WIN_PROJECT_ROOT,
    _powershell_encoded,
    _ssh,
    resolve_windows_host,
)

host = resolve_windows_host()
ps = rf"""
$ProgressPreference = "SilentlyContinue"
$project = "{WIN_PROJECT_ROOT}"
$latest = Join-Path $project ".run\windows_new_framework_months\latest.json"
$runRoot = Join-Path $project ".run\new_framework_month_batch"
$latestObj = $null
if (Test-Path -LiteralPath $latest) {{
  try {{ $latestObj = (Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json) }} catch {{}}
}}
$months = @()
if ($latestObj -and $latestObj.months) {{ $months = @($latestObj.months) }}
if ($months.Count -ge 1) {{
  $tag = (([string]$months[0]).Replace("-", "") + "_" + ([string]$months[$months.Count - 1]).Replace("-", ""))
}} else {{
  $tag = "202603_202601"
}}
$task = "MLT_ModelFeatureStore_$tag"
Write-Output "__TASK_BEGIN__"
try {{
  schtasks /Query /TN $task /V /FO LIST | Select-String "TaskName|Status|Last Run Time|Last Result"
}} catch {{
  Write-Output $_
}}
Write-Output "__TASK_END__"

Write-Output "__RUNSTATUS_BEGIN__"
$runStatus = Join-Path $runRoot "run_status_$tag.txt"
if (Test-Path -LiteralPath $runStatus) {{
  Get-Content -LiteralPath $runStatus -Raw
}} else {{
  Write-Output ""
}}
Write-Output "__RUNSTATUS_END__"

Write-Output "__LATEST_BEGIN__"
if (Test-Path -LiteralPath $latest) {{
  Get-Content -LiteralPath $latest -Raw
}} else {{
  Write-Output "{{}}"
}}
Write-Output "__LATEST_END__"

$state = $null
if (Test-Path -LiteralPath $latest) {{
  try {{ $state = (Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json) }} catch {{}}
}}
$atomicPath = ""
if ($state -and $state.current_month) {{
  $tag = ([string]$state.current_month).Replace("-", "")
  $atomicPath = Join-Path $runRoot "$tag\atomic_state.json"
}}
Write-Output "__ATOMIC_BEGIN__"
if ($atomicPath -and (Test-Path -LiteralPath $atomicPath)) {{
  Get-Content -LiteralPath $atomicPath -Raw
}} else {{
  Write-Output "{{}}"
}}
Write-Output "__ATOMIC_END__"

Write-Output "__PROC_BEGIN__"
$procs = Get-CimInstance Win32_Process | Where-Object {{
  $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_windows_new_framework_months.py*"
}}
foreach ($p in $procs) {{
  Write-Output "$($p.ProcessId)|$($p.CommandLine)"
}}
Write-Output "__PROC_END__"

Write-Output "__LOG_BEGIN__"
$logDir = Join-Path $runRoot "logs"
if (Test-Path -LiteralPath $logDir) {{
  $log = Get-ChildItem -LiteralPath $logDir -Filter "*.out.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($log) {{
    Write-Output "log=$($log.FullName)"
    Get-Content -LiteralPath $log.FullName -Tail 25
  }}
}}
Write-Output "__LOG_END__"
"""

result = _ssh(host, _powershell_encoded(ps), check=False)
text = result.stdout or ""

def section(name: str) -> str:
    start = f"__{name}_BEGIN__"
    end = f"__{name}_END__"
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0].strip()

def load_json(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

latest = load_json(section("LATEST"))
atomic = load_json(section("ATOMIC"))
procs = [line for line in section("PROC").splitlines() if line.strip()]
log_tail = section("LOG")
task_text = section("TASK")
run_status = section("RUNSTATUS")

print(f"Windows: {host}")
if task_text:
    print("任务:")
    print(task_text)
if run_status:
    print("run_status:")
    print(run_status.strip())
if not latest:
    print("状态: 未找到 Windows 月批状态")
else:
    print(f"状态: {latest.get('status')}")
    print(f"月份: {', '.join(latest.get('months') or [])}")
    print(f"当前: {latest.get('current_month') or '-'}")
    print(f"已完成: {', '.join(latest.get('completed_months') or []) or '-'}")
    failed = latest.get("failed_months") or []
    print(f"失败: {failed or '-'}")
if atomic:
    print(
        "当前 atomic: "
        f"status={atomic.get('status')} "
        f"completed_days={len(atomic.get('completed_days') or [])} "
        f"failed_days={len(atomic.get('failed_days') or [])}"
    )
print(f"进程: {'running' if procs else 'not_found'}")
if log_tail:
    print("最近日志:")
    print(log_tail[-3000:])
if result.stderr.strip():
    print("stderr:")
    print(result.stderr.strip()[-1000:])
PY
