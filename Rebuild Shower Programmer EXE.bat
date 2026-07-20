@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ================================================================
rem Shower Programmer one-folder EXE rebuild
rem BUILD_SCRIPT_V11
rem
rem Safe rebuild behavior:
rem - Rebuilds the executable and _internal runtime.
rem - Refreshes program Assets.
rem - Preserves existing local Input, Output, history, manifests,
rem   settings, archives, and user-created runtime data.
rem - Verifies the integrated V11 GUI contract before building.
rem - Runs a self-test inside the staged EXE before deployment.
rem ================================================================

title Rebuild Shower Programmer EXE
cd /d "%~dp0"

set "NO_PAUSE="
if /I "%~1"=="/nopause" set "NO_PAUSE=1"

set "APP_NAME=Shower Programmer"
set "SOURCE_GUI=Backend\shower_programmer_gui.py"
set "SOURCE_BATCH=Backend\shower_batch.py"
set "SOURCE_PROGRAMMER=Backend\shower_programmer.py"
set "SOURCE_CONFIG=Backend\shower_programmer_config.json"
set "ICON_FILE=Assets\ShowersProgrammer.ico"
set "PNG_FILE=Assets\ShowersProgrammer.png"
set "STAGED_DIR=build\release\%APP_NAME%"
set "FINAL_DIR=%APP_NAME%"
set "STAGED_EXE=%STAGED_DIR%\%APP_NAME%.exe"
set "FINAL_EXE=%FINAL_DIR%\%APP_NAME%.exe"

echo.
echo ========================================
echo   Rebuild Shower Programmer EXE
echo ========================================
echo.
echo Project: %CD%
echo.

:check_running
tasklist /FI "IMAGENAME eq %APP_NAME%.exe" 2>NUL | find /I "%APP_NAME%.exe" >NUL
if not errorlevel 1 (
    echo %APP_NAME%.exe is currently running.
    echo Close it before rebuilding so its EXE and runtime files can be replaced safely.
    echo.
    if defined NO_PAUSE (
        echo ERROR: The application is running and this build was started with /nopause.
        goto failed
    )
    set "CONTINUE="
    set /p "CONTINUE=After closing it, type Y and press Enter to check again: "
    if /I not "!CONTINUE!"=="Y" goto cancelled
    echo.
    goto check_running
)

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    set "PY_CMD="%CODEX_PYTHON%""
) else (
    where py >NUL 2>NUL
    if errorlevel 1 (
        echo ERROR: Could not find Python on this build computer.
        echo Install Python, or rebuild from a computer with the Codex runtime installed.
        goto failed
    )
    set "PY_CMD=py -3"
)

echo Using Python:
%PY_CMD% -c "import sys; print('  ' + sys.executable); print('  Python ' + sys.version.split()[0])"
if errorlevel 1 goto failed

call :require_file "%SOURCE_GUI%"
if errorlevel 1 goto failed
call :require_file "%SOURCE_BATCH%"
if errorlevel 1 goto failed
call :require_file "%SOURCE_PROGRAMMER%"
if errorlevel 1 goto failed
call :require_file "%SOURCE_CONFIG%"
if errorlevel 1 goto failed
call :require_file "%ICON_FILE%"
if errorlevel 1 goto failed
call :require_file "%PNG_FILE%"
if errorlevel 1 goto failed

echo.
echo Checking required Python packages...
%PY_CMD% -c "import customtkinter, openpyxl, pypdf, pypdfium2, PIL, reportlab"
if errorlevel 1 (
    echo ERROR: One or more required Python packages are missing.
    echo Install the project dependencies and then run this batch again.
    echo.
    echo Suggested command:
    echo   %PY_CMD% -m pip install pyinstaller customtkinter openpyxl pypdf pypdfium2 pillow reportlab
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

echo Validating configuration JSON...
%PY_CMD% -c "import json, pathlib; json.loads(pathlib.Path(r'%SOURCE_CONFIG%').read_text(encoding='utf-8')); print('  Configuration JSON is valid.')"
if errorlevel 1 goto failed

echo Checking Python syntax for all backend modules...
%PY_CMD% -m py_compile "%SOURCE_GUI%" "%SOURCE_BATCH%" "%SOURCE_PROGRAMMER%"
if errorlevel 1 goto failed

echo Verifying integrated GUI version and Review / Send contracts...
findstr /C:"UPDATE_UI_BATCH_REVIEW_V11" "%SOURCE_GUI%" >NUL
if errorlevel 1 (
    echo ERROR: Backend\shower_programmer_gui.py is not the integrated V11 file.
    echo Replace it with the supplied V11 GUI before rebuilding.
    goto failed
)
%PY_CMD% -c "import sys; sys.path.insert(0, r'%CD%\Backend'); import shower_programmer_gui as gui; gui.validate_runtime_contracts(); print('  GUI runtime contracts passed.')"
if errorlevel 1 (
    echo ERROR: The GUI is missing a required workflow method or contains mixed-version code.
    goto failed
)

set "ICON=%CD%\%ICON_FILE%"

echo.
echo Building one-folder EXE...
echo This commonly takes 1 to 3 minutes depending on the computer.
echo.

%PY_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "%APP_NAME%" ^
  --icon "%ICON%" ^
  --distpath "build\release" ^
  --workpath "build\pyinstaller" ^
  --specpath "build\pyinstaller" ^
  --paths "Backend" ^
  --add-data "%CD%\%SOURCE_CONFIG%;Backend" ^
  --collect-all customtkinter ^
  --collect-all pypdfium2 ^
  "%SOURCE_GUI%"

if errorlevel 1 goto failed

if not exist "%STAGED_EXE%" (
    echo ERROR: Build finished, but the staged EXE was not found:
    echo   %CD%\%STAGED_EXE%
    goto failed
)

echo Running the packaged EXE self-test...
set "SELF_TEST_REPORT=%CD%\build\release\shower_programmer_self_test.json"
if exist "%SELF_TEST_REPORT%" del /F /Q "%SELF_TEST_REPORT%"
start "" /wait "%CD%\%STAGED_EXE%" --self-test "%SELF_TEST_REPORT%"
if errorlevel 1 (
    echo ERROR: The staged EXE reported a failed self-test.
    if exist "%SELF_TEST_REPORT%" type "%SELF_TEST_REPORT%"
    goto failed
)
if not exist "%SELF_TEST_REPORT%" (
    echo ERROR: The staged EXE did not create its self-test report.
    goto failed
)
%PY_CMD% -c "import json, pathlib; p=pathlib.Path(r'%SELF_TEST_REPORT%'); d=json.loads(p.read_text(encoding='utf-8')); assert d.get('ok') is True, d; assert d.get('version') == 'UPDATE_UI_BATCH_REVIEW_V11', d; print('  Packaged EXE self-test passed.')"
if errorlevel 1 (
    type "%SELF_TEST_REPORT%"
    goto failed
)
del /F /Q "%SELF_TEST_REPORT%" >NUL 2>NUL

rem Copy application assets beside the EXE. The current GUI resolves icons
rem from the executable folder, so these must be distributed at the root.
if exist "%STAGED_DIR%\Assets" rmdir /S /Q "%STAGED_DIR%\Assets"
mkdir "%STAGED_DIR%\Assets" >NUL 2>NUL
robocopy "Assets" "%STAGED_DIR%\Assets" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL
if errorlevel 8 (
    echo ERROR: Could not copy Assets into the staged release.
    goto failed
)

rem Include the expected local runtime folder structure in distributed copies.
rem These are empty in a fresh package. Existing user data is preserved when
rem rebuilding because the final deployment does not mirror/delete Input/Output.
if not exist "%STAGED_DIR%\Input\Orders" mkdir "%STAGED_DIR%\Input\Orders"
if not exist "%STAGED_DIR%\Input\Process List" mkdir "%STAGED_DIR%\Input\Process List"
if not exist "%STAGED_DIR%\Output" mkdir "%STAGED_DIR%\Output"
if not exist "%STAGED_DIR%\Output\Runs" mkdir "%STAGED_DIR%\Output\Runs"
if not exist "%STAGED_DIR%\Output\Updates" mkdir "%STAGED_DIR%\Output\Updates"

set "BUILD_SHA="
set "EXE_SHA256="
set "GUI_SHA256="
set "BUILD_TIME="

where git >NUL 2>NUL
if not errorlevel 1 (
    for /f "usebackq delims=" %%I in (`git rev-parse HEAD 2^>NUL`) do set "BUILD_SHA=%%I"
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%STAGED_EXE%').Hash.ToLowerInvariant()"`) do set "EXE_SHA256=%%I"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%SOURCE_GUI%').Hash.ToLowerInvariant()"`) do set "GUI_SHA256=%%I"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'"`) do set "BUILD_TIME=%%I"

if defined BUILD_SHA (
    >"%STAGED_DIR%\.shower_update.json" echo {"sha":"%BUILD_SHA%","exe_sha256":"%EXE_SHA256%","gui_sha256":"%GUI_SHA256%","gui_version":"UPDATE_UI_BATCH_REVIEW_V11","built_at":"%BUILD_TIME%","method":"build"}
) else if defined EXE_SHA256 (
    >"%STAGED_DIR%\.shower_update.json" echo {"exe_sha256":"%EXE_SHA256%","gui_sha256":"%GUI_SHA256%","gui_version":"UPDATE_UI_BATCH_REVIEW_V11","built_at":"%BUILD_TIME%","method":"build"}
)

rem Refresh only program-controlled build files. Do not remove Input, Output,
rem processing_history.json, import manifests, UI settings, or local archives.
if not exist "%FINAL_DIR%" mkdir "%FINAL_DIR%"
if exist "%FINAL_DIR%\_internal" rmdir /S /Q "%FINAL_DIR%\_internal"
if exist "%FINAL_EXE%" del /F /Q "%FINAL_EXE%"
if exist "%FINAL_DIR%\Assets" rmdir /S /Q "%FINAL_DIR%\Assets"
if exist "%FINAL_DIR%\.shower_update.json" del /F /Q "%FINAL_DIR%\.shower_update.json"

robocopy "%STAGED_DIR%" "%FINAL_DIR%" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL
if errorlevel 8 (
    echo ERROR: Could not copy the staged release into the final %APP_NAME% folder.
    goto failed
)

call :require_file "%FINAL_EXE%"
if errorlevel 1 goto failed
call :require_file "%FINAL_DIR%\_internal\pypdfium2_raw\pdfium.dll"
if errorlevel 1 (
    echo The Review Order preview may be slow or fail without pdfium.dll.
    goto failed
)
call :require_file "%FINAL_DIR%\_internal\Backend\shower_programmer_config.json"
if errorlevel 1 (
    echo The CNC configuration was not included in the bundled runtime.
    goto failed
)
call :require_file "%FINAL_DIR%\Assets\ShowersProgrammer.ico"
if errorlevel 1 goto failed
call :require_file "%FINAL_DIR%\Assets\ShowersProgrammer.png"
if errorlevel 1 goto failed

if not exist "%FINAL_DIR%\Input\Orders" mkdir "%FINAL_DIR%\Input\Orders"
if not exist "%FINAL_DIR%\Input\Process List" mkdir "%FINAL_DIR%\Input\Process List"
if not exist "%FINAL_DIR%\Output" mkdir "%FINAL_DIR%\Output"
if not exist "%FINAL_DIR%\Output\Runs" mkdir "%FINAL_DIR%\Output\Runs"
if not exist "%FINAL_DIR%\Output\Updates" mkdir "%FINAL_DIR%\Output\Updates"

echo.
echo ========================================
echo   Build complete
echo ========================================
echo.
echo EXE:
echo   %CD%\%FINAL_EXE%
echo.
if defined EXE_SHA256 echo EXE SHA-256: %EXE_SHA256%
if defined GUI_SHA256 echo GUI SHA-256: %GUI_SHA256%
if defined BUILD_SHA echo Git commit: %BUILD_SHA%
if defined BUILD_TIME echo Built at: %BUILD_TIME%
echo.
echo When giving this to another user, send the whole folder:
echo   %CD%\%FINAL_DIR%
echo.
echo Python is required only on the computer performing this build.
echo Users running the completed EXE do not need Python installed.
echo.

if defined NO_PAUSE exit /b 0

set "LAUNCH="
set /p "LAUNCH=Launch Shower Programmer now? [y/N]: "
if /I "%LAUNCH%"=="Y" start "" "%CD%\%FINAL_EXE%"
pause
exit /b 0

:require_file
if not exist "%~1" (
    echo ERROR: Missing required file:
    echo   %~1
    exit /b 1
)
exit /b 0

:cancelled
echo.
echo Build cancelled.
if defined NO_PAUSE exit /b 2
pause
exit /b 2

:failed
echo.
echo Build failed. Read the error above, correct it, and run this batch again.
if defined NO_PAUSE exit /b 1
pause
exit /b 1
