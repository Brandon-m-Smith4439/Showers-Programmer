@echo off
setlocal
cd /d "%~dp0.."

set "SCRIPT=%~dp0shower_programmer.py"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" "%SCRIPT%" %*
) else (
  py -3 "%SCRIPT%" %*
)
