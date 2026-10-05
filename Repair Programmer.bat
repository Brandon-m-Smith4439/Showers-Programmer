@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0Repair Programmer.ps1"
if errorlevel 1 (
  echo Repair did not complete. Review the message above; do not delete your Input or Output folders.
  pause
  exit /b 1
)
exit /b 0
