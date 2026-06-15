param(
  [string]$ArchivePath = 'D:\MarketData\202604\20260401.7z',
  [string]$OutDir = 'G:\atomic_extract_full_test',
  [ValidateSet('7z','tar')][string]$Mode = '7z'
)
$ErrorActionPreference = 'Stop'
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Path $OutDir | Out-Null
$sw = [System.Diagnostics.Stopwatch]::StartNew()
if ($Mode -eq '7z') {
  & 'C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe' x -y $ArchivePath ('-o' + $OutDir) | Out-Null
} else {
  tar -xf $ArchivePath -C $OutDir
}
$sw.Stop()
$count = (Get-ChildItem -Force -Recurse $OutDir | Measure-Object).Count
[pscustomobject]@{
  mode = $Mode
  seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
  extracted_items = $count
  out_dir = $OutDir
} | ConvertTo-Json -Compress
