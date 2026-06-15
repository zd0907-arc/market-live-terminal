param(
  [string]$ConfigPath,
  [string]$Tag = 'atomic_backfill'
)
$ErrorActionPreference = 'Stop'
$root = 'D:\market-live-terminal'
$py = 'C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe'
$script = Join-Path $root 'backend\scripts\run_atomic_backfill_windows.py'
$runDir = Join-Path $root '.run'
if (!(Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $runDir ($Tag + '_' + $ts + '.log')
$stderr = Join-Path $runDir ($Tag + '_' + $ts + '.err.log')
$p = Start-Process -FilePath $py -WorkingDirectory $root -ArgumentList @('-u', $script, '--config', $ConfigPath) -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
[pscustomobject]@{
  pid = $p.Id
  config = $ConfigPath
  log_path = $stdout
  err_path = $stderr
  started_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
} | ConvertTo-Json -Compress
