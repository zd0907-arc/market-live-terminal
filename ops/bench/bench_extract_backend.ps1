param(
  [string]$ArchivePath = 'D:\MarketData\202604\20260401.7z',
  [string]$OutRoot = 'G:\atomic_extract_bench_compare',
  [int]$Seconds = 30
)
$ErrorActionPreference = 'Stop'
if (Test-Path $OutRoot) { Remove-Item -Recurse -Force $OutRoot }
New-Item -ItemType Directory -Path $OutRoot | Out-Null

function Stop-ByName($name) {
  Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} }
}

function Run-Bench($tag, $filePath, $argList, $processName) {
  $out = Join-Path $OutRoot $tag
  if (Test-Path $out) { Remove-Item -Recurse -Force $out }
  New-Item -ItemType Directory -Path $out | Out-Null
  $args = @()
  foreach ($a in $argList) {
    $args += ($a -replace '__ARCHIVE__', $ArchivePath -replace '__OUT__', $out)
  }
  $p = Start-Process -FilePath $filePath -ArgumentList $args -PassThru
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
  if (Test-Path $out) { try { $count = (Get-ChildItem -Force -Recurse $out | Measure-Object).Count } catch {} }
  Stop-ByName $processName
  return [pscustomobject]@{ tag=$tag; alive_after=$alive; cpu=$cpu; extracted_items=$count; out_dir=$out }
}

$seven = 'C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe'
$res = @()
if (Test-Path $seven) {
  $res += Run-Bench '7z_default' $seven @('x','-y','__ARCHIVE__','-o__OUT__') '7z'
}
$res += Run-Bench 'tar_builtin' 'tar' @('-xf','__ARCHIVE__','-C','__OUT__') 'tar'
$res | ConvertTo-Json -Depth 4
