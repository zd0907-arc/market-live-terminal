param(
  [string]$ArchivePath = 'D:\MarketData\202604\20260401.7z',
  [string]$OutRoot = 'G:\atomic_extract_bench',
  [int]$Seconds = 30
)
$ErrorActionPreference = 'Stop'
$seven = 'C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe'
if (!(Test-Path $seven)) { throw '7z not found' }
if (Test-Path $OutRoot) { Remove-Item -Recurse -Force $OutRoot }
New-Item -ItemType Directory -Path $OutRoot | Out-Null

function Run-Bench($tag, $args) {
  $out = Join-Path $OutRoot $tag
  if (Test-Path $out) { Remove-Item -Recurse -Force $out }
  New-Item -ItemType Directory -Path $out | Out-Null
  $p = Start-Process -FilePath $seven -ArgumentList ($args + @($ArchivePath, '-o' + $out)) -PassThru -WindowStyle Hidden
  Start-Sleep -Seconds $Seconds
  $alive = $false
  $cpu = $null
  try {
    $gp = Get-Process -Id $p.Id -ErrorAction Stop
    $alive = $true
    $cpu = $gp.CPU
    Stop-Process -Id $p.Id -Force
  } catch {}
  $count = 0
  if (Test-Path $out) {
    try { $count = (Get-ChildItem -Force -Recurse $out | Measure-Object).Count } catch {}
  }
  return [pscustomobject]@{ tag=$tag; alive_after=$alive; cpu=$cpu; extracted_items=$count; out_dir=$out }
}

$res = @()
$res += Run-Bench 'default' @('x','-y')
$res += Run-Bench 'mmt8' @('x','-y','-mmt=8')
$res | ConvertTo-Json -Depth 4
