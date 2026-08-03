@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
set "SCRIPT=%~dp0shower_programmer_v4.py"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" "%SCRIPT%" --batch %*
  exit /b %ERRORLEVEL%
)
where py >NUL 2>NUL
if not errorlevel 1 (
  py -3 "%SCRIPT%" --batch %*
  exit /b %ERRORLEVEL%
)
python "%SCRIPT%" --batch %*
exit /b %ERRORLEVEL%
