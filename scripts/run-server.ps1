# WiFiSense server runner — auto-restart kalau node crash.
# Jalankan: .\scripts\run-server.ps1
# Stop: Ctrl+C, atau Stop-Process -Name node
# Log: server/server.log

param(
  [int]$UdpPort = 5005,
  [int]$HttpPort = 3000,
  [int]$WsPort = 8080
)

$ErrorActionPreference = 'Continue'
$serverDir = "$PSScriptRoot\..\server"
$logFile = "$serverDir\server.log"

Write-Host "=== WiFiSense server (UDP $UdpPort -> HTTP $HttpPort / WS $WsPort) ===" -ForegroundColor Cyan
Write-Host "Log: $logFile"
Write-Host "Stop dengan Ctrl+C" -ForegroundColor Yellow

$env:UDP_PORT = "$UdpPort"
$env:HTTP_PORT = "$HttpPort"
$env:WS_PORT = "$WsPort"

Set-Location -LiteralPath $serverDir
if (-not (Test-Path -LiteralPath "$serverDir\node_modules")) {
  Write-Host "node_modules belum ada, npm install dulu..." -ForegroundColor Yellow
  npm install
}

$n = 0
while ($true) {
  $n++
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $logFile -Value "[$ts] (run #$n) node index.js start"
  Write-Host "[$ts] run #$n — node index.js" -ForegroundColor Green
  node index.js 2>&1 | ForEach-Object { $_; Add-Content -LiteralPath $logFile -Value $_ }
  $code = $LASTEXITCODE
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $logFile -Value "[$ts] (run #$n) exit code $code — restart 3 detik..."
  Write-Host "[$ts] exit $code — restart 3 detik... (Ctrl+C untuk stop)" -ForegroundColor Red
  Start-Sleep -Seconds 3
}
