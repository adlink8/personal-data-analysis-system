@echo off
chcp 65001 >nul
title Stop Personal Data Services
echo Stopping Personal Data Services ...
echo.
pwsh -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "foreach ($port in 8000,8789,8081) { Get-NetTCPConnection -State Listen -LocalPort $port | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force } };" ^
  "Get-Process tunnel-client,rag-api -ErrorAction SilentlyContinue | Stop-Process -Force;" ^
  "Get-CimInstance Win32_Process -Filter \"Name='pwsh.exe'\" | Where-Object { $_.CommandLine -match 'start-services' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force };" ^
  "Start-Sleep 2;" ^
  "Write-Host '--- port state ---';" ^
  "foreach ($p in 8000,8789,8081) { Write-Host ('PORT ' + $p + ' busy=' + [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)) }"
echo.
echo Done. Press any key to close.
pause >nul
