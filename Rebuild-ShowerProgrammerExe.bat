@echo off
setlocal EnableExtensions

title Rebuild Shower Programmer EXE
cd /d "%~dp0"

set "NO_PAUSE="
if /I "%~1"=="/nopause" set "NO_PAUSE=1"

echo.
echo ========================================
echo   Rebuild Shower Programmer EXE
echo ========================================
echo.
echo Project: %CD%
echo.

tasklist /FI "IMAGENAME eq Shower Programmer.exe" 2>NUL | find /I "Shower Programmer.exe" >NUL
if not errorlevel 1 (
    echo Shower Programmer.exe appears to be running.
    echo Close Shower Programmer before rebuilding, otherwise PyInstaller may not be able to replace the folder.
    echo.
    set /p "CONTINUE=After closing it, type Y and press Enter to continue: "
    if /I not "%CONTINUE%"=="Y" goto cancelled
)

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    set "PY_CMD="%CODEX_PYTHON%""
) else (
    where py >NUL 2>NUL
    if errorlevel 1 (
        echo ERROR: Could not find Python.
        echo Install Python or rebuild from a machine that has the Codex runtime installed.
        goto failed
    )
    set "PY_CMD=py -3"
)

if not exist "Backend\shower_programmer_gui.py" (
    echo ERROR: Missing Backend\shower_programmer_gui.py
    goto failed
)

if not exist "Assets\ShowersProgrammer.ico" (
    echo ERROR: Missing Assets\ShowersProgrammer.ico
    goto failed
)

echo Checking PyInstaller...
%PY_CMD% -m PyInstaller --version >NUL 2>NUL
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed for this Python.
    echo Try this, then run this batch again:
    echo.
    echo   %PY_CMD% -m pip install pyinstaller
    echo.
    goto failed
)

echo Checking Python syntax...
%PY_CMD% -m py_compile "Backend\shower_programmer_gui.py"
if errorlevel 1 goto failed

set "ICON=%CD%\Assets\ShowersProgrammer.ico"

echo.
echo Building fast one-folder EXE...
echo This usually takes about 1 minute.
echo.

%PY_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "Shower Programmer" ^
  --icon "%ICON%" ^
  --distpath "." ^
  --workpath "build\pyinstaller" ^
  --specpath "build\pyinstaller" ^
  --paths "Backend" ^
  --collect-all customtkinter ^
  --collect-all pypdfium2 ^
  "Backend\shower_programmer_gui.py"

if errorlevel 1 goto failed

if not exist "Shower Programmer\Shower Programmer.exe" (
    echo ERROR: Build finished, but the final EXE was not found.
    goto failed
)

if not exist "Shower Programmer\_internal\pypdfium2_raw\pdfium.dll" (
    echo ERROR: Build finished, but pypdfium2/pdfium.dll was not included.
    echo The Review Order preview may be slow or fail without this file.
    goto failed
)

echo.
echo ========================================
echo   Build complete
echo ========================================
echo.
echo EXE:
echo   %CD%\Shower Programmer\Shower Programmer.exe
echo.
echo When giving this to someone else, send the whole folder:
echo   %CD%\Shower Programmer
echo.

if defined NO_PAUSE exit /b 0

set /p "LAUNCH=Launch Shower Programmer now? [y/N]: "
if /I "%LAUNCH%"=="Y" start "" "%CD%\Shower Programmer\Shower Programmer.exe"
pause
exit /b 0

:cancelled
echo.
echo Build cancelled.
if defined NO_PAUSE exit /b 2
pause
exit /b 2

:failed
echo.
echo Build failed. Read the error above, fix it, then run this batch again.
if defined NO_PAUSE exit /b 1
pause
exit /b 1
