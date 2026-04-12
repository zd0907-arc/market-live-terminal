param(
  [string]$ConfigPath,
  [int]$Seconds = 180
)
$ErrorActionPreference = 'Stop'
$root = 'D:\market-live-terminal'
$py = 'C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe'
$script = Join-Path $root 'backend\scripts\run_atomic_backfill_windows.py'
$runDir = Join-Path $root '.run'
if (!(Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }

# 仅清理同一 bench 的旧进程，避免误杀正式任务
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_atomic_backfill_windows.py*bench_20260410*'
} | ForEach-Object {
  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
foreach ($p in @($config.atomic_db, $config.state_file, $config.report_file)) {
  if ($p -and (Test-Path $p)) { Remove-Item -Force $p }
}
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $runDir ("short_bench_" + $ts + '.log')
$stderr = Join-Path $runDir ("short_bench_" + $ts + '.err.log')
$argList = @('-u', $script, '--config', $ConfigPath)
$p = Start-Process -FilePath $py -ArgumentList $argList -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden
Start-Sleep -Seconds $Seconds

$alive = $false
$cpu = $null
try {
  $proc = Get-Process -Id $p.Id -ErrorAction Stop
  $alive = $true
  $cpu = [double]::Parse(($proc.CPU.ToString()))
  Stop-Process -Id $p.Id -Force
} catch {}

$state = $null
$report = $null
if (Test-Path $config.state_file) { $state = Get-Content $config.state_file -Raw | ConvertFrom-Json }
if (Test-Path $config.report_file) { $report = Get-Content $config.report_file -Raw | ConvertFrom-Json }

$lastLogLine = $null
$lastErrLine = $null
$logSize = $null
$errSize = $null

$tradeDailyRows = $null
$orderDailyRows = $null
$bookDailyRows = $null
$trade5mRows = $null
if ($config.atomic_db -and (Test-Path $config.atomic_db)) {
  try {
    $dbStatsJson = & $py -c "import json, sqlite3, sys; conn=sqlite3.connect(sys.argv[1]); cur=conn.cursor(); stats={'trade_daily_rows': cur.execute('select count(*) from atomic_trade_daily').fetchone()[0], 'order_daily_rows': cur.execute('select count(*) from atomic_order_daily').fetchone()[0], 'book_daily_rows': cur.execute('select count(*) from atomic_book_state_daily').fetchone()[0], 'trade_5m_rows': cur.execute('select count(*) from atomic_trade_5m').fetchone()[0]}; print(json.dumps(stats, ensure_ascii=False))" $config.atomic_db
    if ($dbStatsJson) {
      $dbStats = $dbStatsJson | ConvertFrom-Json
      $tradeDailyRows = $dbStats.trade_daily_rows
      $orderDailyRows = $dbStats.order_daily_rows
      $bookDailyRows = $dbStats.book_daily_rows
      $trade5mRows = $dbStats.trade_5m_rows
    }
  } catch {}
}
if (Test-Path $stdout) {
  $logSize = (Get-Item $stdout).Length
  $tmp = [string[]](Get-Content $stdout -Tail 1)
  if ($tmp.Count -gt 0) { $lastLogLine = [string]$tmp[-1] }
}
if (Test-Path $stderr) {
  $errSize = (Get-Item $stderr).Length
  $tmp = [string[]](Get-Content $stderr -Tail 1)
  if ($tmp.Count -gt 0) { $lastErrLine = [string]$tmp[-1] }
}

[pscustomobject]@{
  config = $ConfigPath
  seconds = $Seconds
  pid = $p.Id
  alive_after_window = $alive
  cpu_seconds = $cpu
  state_status = if ($state) { $state.status } else { $null }
  completed_days = if ($state) { $state.completed_days.Count } else { $null }
  failed_days = if ($state) { $state.failed_days.Count } else { $null }
  report_day_count = if ($report) { $report.completed_day_count } else { $null }
  log_path = $stdout
  log_size = $logSize
  last_log_line = $lastLogLine
  err_path = $stderr
  err_size = $errSize
  last_err_line = $lastErrLine
  trade_daily_rows = $tradeDailyRows
  order_daily_rows = $orderDailyRows
  book_daily_rows = $bookDailyRows
  trade_5m_rows = $trade5mRows
  symbols_per_min = if ($tradeDailyRows -ne $null -and $Seconds -gt 0) { [math]::Round(($tradeDailyRows * 60.0) / $Seconds, 2) } else { $null }
} | ConvertTo-Json -Depth 4 -Compress
