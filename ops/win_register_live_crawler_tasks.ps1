param(
    [string]$ProjectRoot = 'D:\market-live-terminal',
    [string]$TaskName = 'ZhangDataLiveCrawler',
    [string]$PythonExe = 'C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe',
    [string]$CloudApiUrl = 'http://111.229.144.202'
)

$ErrorActionPreference = 'Stop'
$runLog = Join-Path $ProjectRoot '.run\live_crawler_task_setup.log'
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot '.run') | Out-Null

function Write-SetupLog {
    param([string]$Message)
    $line = "[{0}] [TASK-SETUP] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $runLog -Value $line
    Write-Host $line
}

function Resolve-EnvValue {
    param([string]$Name, [string]$Default = '')
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { $value = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if ([string]::IsNullOrWhiteSpace($value)) { $value = [Environment]::GetEnvironmentVariable($Name, 'Machine') }
    if ([string]::IsNullOrWhiteSpace($value)) { $value = $Default }
    return $value
}

function Invoke-Schtasks {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$IgnoreFailure
    )

    & schtasks.exe @Arguments | Out-Null
    if (-not $IgnoreFailure -and $LASTEXITCODE -ne 0) {
        throw ("schtasks failed: schtasks.exe {0} (exit={1})" -f ($Arguments -join ' '), $LASTEXITCODE)
    }
}

function Stop-LegacyCrawlerProcesses {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -ieq 'python.exe' -and
            $_.CommandLine -and
            $_.CommandLine.IndexOf('backend\scripts\live_crawler_win.py', [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        }

    foreach ($proc in $procs) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-SetupLog ("stopped legacy crawler pid={0}" -f $proc.ProcessId)
        }
        catch {
            Write-SetupLog ("warn: failed to stop legacy crawler pid={0}: {1}" -f $proc.ProcessId, $_.Exception.Message)
        }
    }
}

$batchPath = Join-Path $ProjectRoot 'start_live_crawler.bat'
if (-not (Test-Path $batchPath)) {
    throw "Missing batch path: $batchPath"
}

$ingestToken = Resolve-EnvValue -Name 'INGEST_TOKEN'
if ([string]::IsNullOrWhiteSpace($ingestToken)) {
    throw 'INGEST_TOKEN missing in Process/User/Machine scope; refuse to register task'
}
$cloudApi = Resolve-EnvValue -Name 'CLOUD_API_URL' -Default $CloudApiUrl
$focus = Resolve-EnvValue -Name 'FOCUS_TICK_INTERVAL_SECONDS' -Default '5'
$warm = Resolve-EnvValue -Name 'WARM_TICK_INTERVAL_SECONDS' -Default '30'
$fullSweep = Resolve-EnvValue -Name 'FULL_SWEEP_INTERVAL_SECONDS' -Default '900'
$timeout = Resolve-EnvValue -Name 'AKSHARE_TICK_TIMEOUT_SECONDS' -Default '15'

[Environment]::SetEnvironmentVariable('INGEST_TOKEN', $ingestToken, 'Machine')
[Environment]::SetEnvironmentVariable('CLOUD_API_URL', $cloudApi, 'Machine')
[Environment]::SetEnvironmentVariable('PYTHON_EXE', $PythonExe, 'Machine')
[Environment]::SetEnvironmentVariable('FOCUS_TICK_INTERVAL_SECONDS', $focus, 'Machine')
[Environment]::SetEnvironmentVariable('WARM_TICK_INTERVAL_SECONDS', $warm, 'Machine')
[Environment]::SetEnvironmentVariable('FULL_SWEEP_INTERVAL_SECONDS', $fullSweep, 'Machine')
[Environment]::SetEnvironmentVariable('AKSHARE_TICK_TIMEOUT_SECONDS', $timeout, 'Machine')
Write-SetupLog 'machine env refreshed for crawler task'

$startBoundary = (Get-Date).ToString('s')
$xmlPath = Join-Path $env:TEMP 'zhangdata_live_crawler_task.xml'
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ZhangData live crawler with boot + 5 minute restart triggers</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <Duration>P9999D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c &quot;$batchPath&quot;</Arguments>
      <WorkingDirectory>$ProjectRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
Set-Content -Path $xmlPath -Value $taskXml -Encoding Unicode

Invoke-Schtasks -Arguments @('/Delete', '/TN', $TaskName, '/F') -IgnoreFailure
Invoke-Schtasks -Arguments @('/Delete', '/TN', 'ZhangDataLiveCrawlerWatchdog', '/F') -IgnoreFailure
Stop-LegacyCrawlerProcesses
Remove-Item -Path (Join-Path $ProjectRoot '.run\live_crawler.pid') -Force -ErrorAction SilentlyContinue
Invoke-Schtasks -Arguments @('/Create', '/TN', $TaskName, '/XML', $xmlPath, '/F')
Write-SetupLog "registered task $TaskName via XML (boot + 5m repetition + IgnoreNew)"

Invoke-Schtasks -Arguments @('/Run', '/TN', $TaskName)
Write-SetupLog "triggered task $TaskName once for immediate recovery"

& schtasks.exe /Query /TN $TaskName /V /FO LIST
if ($LASTEXITCODE -ne 0) {
    throw "schtasks query failed for $TaskName (exit=$LASTEXITCODE)"
}
