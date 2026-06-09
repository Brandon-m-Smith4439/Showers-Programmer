@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=%~dp0Backend\shower_programmer_gui.py"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
  start "" "%BUNDLED_PY%" "%SCRIPT%"
) else (
  start "" py -3 "%SCRIPT%"
)
