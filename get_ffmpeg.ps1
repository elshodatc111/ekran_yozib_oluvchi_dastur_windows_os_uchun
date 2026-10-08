# FFmpeg ni yuklab, ffmpeg\ffmpeg.exe ga joylaydi.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $root "ffmpeg"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$zip = Join-Path $env:TEMP "ffmpeg-release-essentials.zip"
$tmp = Join-Path $env:TEMP "ffmpeg_extract"
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

Write-Host "Yuklanmoqda: $url"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$exe = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
if (-not $exe) { throw "ffmpeg.exe arxivda topilmadi" }
Copy-Item $exe.FullName (Join-Path $dest "ffmpeg.exe") -Force
Remove-Item -Recurse -Force $tmp
Remove-Item -Force $zip
Write-Host "Tayyor: $dest\ffmpeg.exe"
