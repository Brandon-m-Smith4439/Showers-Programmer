@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=%~dp0Backend\shower_programmer_v4.py"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
  start "" "%BUNDLED_PY%" "%SCRIPT%"
  exit /b 0
)

where py >NUL 2>NUL
if not errorlevel 1 (
  start "" py -3 "%SCRIPT%"
  exit /b 0
)

where python >NUL 2>NUL
if not errorlevel 1 (
  start "" python "%SCRIPT%"
  exit /b 0
)

echo ERROR: Python was not found.
echo Install Python 3 or run the packaged Shower Programmer.exe.
pause
exit /b 1
