@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Shower Programmer - First-Time Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0First-Time Setup.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not complete. Review the error above before trying again.
  pause
  exit /b 1
)
echo.
echo Setup complete. You can use the Shower Programmer desktop shortcut next time.
echo To keep its icon on the taskbar, right-click the running app icon and choose Pin to taskbar.
pause
exit /b 0
