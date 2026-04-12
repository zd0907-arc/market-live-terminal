param(
  [string]$ArchivePath = 'D:\MarketData\202604\20260401.7z',
  [int]$Seconds = 30
)
$ErrorActionPreference = 'Stop'
function Run-Bench($tag, $out) {
  if (Test-Path $out) { Remove-Item -Recurse -Force $out }
  New-Item -ItemType Directory -Path $out | Out-Null
  $p = Start-Process -FilePath 'tar' -ArgumentList @('-xf', $ArchivePath, '-C', $out) -PassThru
  Start-Sleep -Seconds $Seconds
  $alive = $false; $cpu = $null
  try { $gp = Get-Process -Id $p.Id -ErrorAction Stop; $alive = $true; $cpu = $gp.CPU; Stop-Process -Id $p.Id -Force } catch {}
  $count = 0
  if (Test-Path $out) { try { $count = (Get-ChildItem -Force -Recurse $out | Measure-Object).Count } catch {} }
  [pscustomobject]@{ tag=$tag; alive_after=$alive; cpu=$cpu; extracted_items=$count; out_dir=$out }
}
$res = @()
$res += Run-Bench 'tar_G' 'G:\atomic_extract_bench_g'
$res += Run-Bench 'tar_Z' 'Z:\atomic_extract_bench_z'
$res | ConvertTo-Json -Depth 4
