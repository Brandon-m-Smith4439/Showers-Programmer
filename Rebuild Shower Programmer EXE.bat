@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ==================================================================
rem Shower Programmer metadata-driven one-folder EXE rebuild
rem BUILD_SCRIPT_RELEASE_METADATA_DRIVEN
rem
rem Builds from Backend\shower_programmer_v4.py so the established core
rem and the isolated current-release production-safety layer are packaged together.
rem Existing Input, Output, settings, histories, archives, and overrides
rem are preserved during deployment.
rem ==================================================================

cd /d "%~dp0"
title Rebuild Shower Programmer EXE

set "NO_PAUSE="
if /I "%~1"=="/nopause" set "NO_PAUSE=1"

set "APP_NAME=Shower Programmer"
set "SOURCE_ENTRY=Backend\shower_programmer_v4.py"
set "SOURCE_FEATURES=Backend\shower_v4_features.py"
set "SOURCE_GUI=Backend\shower_programmer_gui.py"
set "SOURCE_BATCH=Backend\shower_batch.py"
set "SOURCE_PROGRAMMER=Backend\shower_programmer.py"
set "SOURCE_CONFIG=Backend\shower_programmer_config.json"
set "SOURCE_VERSION=Backend\version.json"
set "SOURCE_CHANGELOG=CHANGELOG.md"
set "SOURCE_PACKAGE_BUILDER=Backend\build_update_package.py"
set "ICON_FILE=Assets\ShowersProgrammer.ico"
set "PNG_FILE=Assets\ShowersProgrammer.png"
set "STAGED_DIR=build\release\%APP_NAME%"
set "STAGED_EXE=%STAGED_DIR%\%APP_NAME%.exe"
set "FINAL_DIR=%APP_NAME%"
set "UPDATE_RELEASE_DIR=release"
set "UPDATE_ZIP=%UPDATE_RELEASE_DIR%\Shower-Programmer-Windows.zip"
set "UPDATE_METADATA=%UPDATE_RELEASE_DIR%\Shower-Programmer-Windows.json"
set "SOURCE_SELF_TEST=build\source_release_self_test.json"
set "PACKAGED_SELF_TEST=build\release\packaged_release_self_test.json"
set "REQUIRED_FLAGS=v4_conflict_safe_send,v4_existing_file_keep_or_replace,v4_per_file_send_failure_continuation,v4_radius_preview_callouts,v4_long_glass_se_validation,v4_waterjet_oversize_flag,v4_waterjet_thickness_radius_validation,v4_split_batch_order_merge,version_0_5_radius_label_spacing,version_0_5_oos_callout_avoidance,version_0_5_radius_header_removed,version_0_6_fps_rake_orientation,version_0_6_dynamic_release_self_test"

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
    echo ERROR: %APP_NAME%.exe is currently running.
    echo Close it before rebuilding so the runtime can be replaced safely.
    if defined NO_PAUSE goto failed
    echo.
    set "CONTINUE="
    set /p "CONTINUE=After closing it, type Y and press Enter to check again: "
    if /I not "!CONTINUE!"=="Y" goto cancelled
    goto check_running
)

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PYTHON_EXE="
set "PYTHON_ARGS="
if exist "%CODEX_PYTHON%" (
    set "PYTHON_EXE=%CODEX_PYTHON%"
) else (
    where py >NUL 2>NUL
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
    ) else (
        where python >NUL 2>NUL
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)
if not defined PYTHON_EXE (
    echo ERROR: Python 3 was not found on this computer.
    echo Install Python 3, or rebuild from a computer with the Codex runtime.
    goto failed
)

echo Using Python:
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; print('  ' + sys.executable); print('  Python ' + sys.version.split()[0])"
if errorlevel 1 goto failed

for %%F in (
    "%SOURCE_ENTRY%"
    "%SOURCE_FEATURES%"
    "%SOURCE_GUI%"
    "%SOURCE_BATCH%"
    "%SOURCE_PROGRAMMER%"
    "%SOURCE_CONFIG%"
    "%SOURCE_VERSION%"
    "%SOURCE_CHANGELOG%"
    "%SOURCE_PACKAGE_BUILDER%"
    "%ICON_FILE%"
    "%PNG_FILE%"
) do (
    if not exist "%%~F" (
        echo ERROR: Missing required file:
        echo   %%~F
        goto failed
    )
)

echo.
echo Checking required Python packages...
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import customtkinter, openpyxl, pypdf, pypdfium2, PIL, reportlab, PyInstaller; print('  Required packages are available.')"
if errorlevel 1 (
    echo ERROR: One or more required Python packages are missing.
    echo Suggested command:
    echo   "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install pyinstaller customtkinter openpyxl pypdf pypdfium2 pillow reportlab
    goto failed
)

echo Validating release metadata, changelog, configuration, and release marker...
if not exist build mkdir build
set "VERSION_INFO_FILE=build\version_info_%RANDOM%_%RANDOM%.txt"
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import json,pathlib,re; v=json.loads(pathlib.Path(r'%SOURCE_VERSION%').read_text(encoding='utf-8')); required=('version','version_number','marker','release_name','release_date'); missing=[k for k in required if not str(v.get(k,'')).strip()]; assert not missing, missing; assert re.fullmatch(r'Version \d+\.\d+',str(v['version'])),v; assert int(v['version_number']) > 0,v; c=pathlib.Path(r'%SOURCE_CHANGELOG%').read_text(encoding='utf-8'); assert '## ['+str(v['version'])+']' in c; json.loads(pathlib.Path(r'%SOURCE_CONFIG%').read_text(encoding='utf-8')); print('APP_VERSION='+str(v['version'])); print('APP_MARKER='+str(v['marker'])); print('APP_RELEASE_NAME='+str(v['release_name']))" > "%VERSION_INFO_FILE%"
if errorlevel 1 goto failed
for /f "usebackq tokens=1,* delims==" %%A in ("%VERSION_INFO_FILE%") do (
    if /I "%%A"=="APP_VERSION" set "APP_VERSION=%%B"
    if /I "%%A"=="APP_MARKER" set "APP_MARKER=%%B"
    if /I "%%A"=="APP_RELEASE_NAME" set "APP_RELEASE_NAME=%%B"
)
del /F /Q "%VERSION_INFO_FILE%" >NUL 2>NUL
if not defined APP_VERSION goto failed
if not defined APP_MARKER goto failed
findstr /C:"%APP_MARKER%" "%SOURCE_FEATURES%" >NUL
if errorlevel 1 (
    echo ERROR: %SOURCE_FEATURES% does not contain the release marker %APP_MARKER%.
    goto failed
)
echo   Release %APP_VERSION%: %APP_RELEASE_NAME%

echo Checking Python syntax...
"%PYTHON_EXE%" %PYTHON_ARGS% -m py_compile "%SOURCE_ENTRY%" "%SOURCE_FEATURES%" "%SOURCE_GUI%" "%SOURCE_BATCH%" "%SOURCE_PROGRAMMER%" "%SOURCE_PACKAGE_BUILDER%"
if errorlevel 1 goto failed

echo Running focused release unit tests...
"%PYTHON_EXE%" %PYTHON_ARGS% -m unittest discover -s tests -v
if errorlevel 1 goto failed

echo Running integrated source self-test...
if exist "%SOURCE_SELF_TEST%" del /F /Q "%SOURCE_SELF_TEST%" >NUL 2>NUL
"%PYTHON_EXE%" %PYTHON_ARGS% "%SOURCE_ENTRY%" --self-test "%SOURCE_SELF_TEST%"
if errorlevel 1 (
    echo ERROR: Integrated source self-test failed.
    if exist "%SOURCE_SELF_TEST%" type "%SOURCE_SELF_TEST%"
    goto failed
)
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import json,pathlib; d=json.loads(pathlib.Path(r'%SOURCE_SELF_TEST%').read_text(encoding='utf-8')); flags=r'%REQUIRED_FLAGS%'.split(','); assert d.get('ok') is True,d; assert d.get('display_version')==r'%APP_VERSION%',d; assert d.get('version')==r'%APP_MARKER%',d; missing=[k for k in flags if d.get(k) is not True]; assert not missing,missing; print('  Integrated source self-test passed.')"
if errorlevel 1 goto failed

set "BUILD_SHA="
where git >NUL 2>NUL
if not errorlevel 1 (
    for /f "usebackq delims=" %%G in (`git rev-parse HEAD 2^>NUL`) do set "BUILD_SHA=%%G"
)
if not defined BUILD_SHA set "BUILD_SHA=uncommitted-release-build"

echo.
echo Cleaning generated build folders...
if exist "build\pyinstaller" rmdir /S /Q "build\pyinstaller"
if exist "%STAGED_DIR%" rmdir /S /Q "%STAGED_DIR%"
if exist "%PACKAGED_SELF_TEST%" del /F /Q "%PACKAGED_SELF_TEST%" >NUL 2>NUL

echo Building one-folder EXE...
"%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "%APP_NAME%" ^
  --icon "%CD%\%ICON_FILE%" ^
  --distpath "build\release" ^
  --workpath "build\pyinstaller" ^
  --specpath "build\pyinstaller" ^
  --paths "Backend" ^
  --add-data "%CD%\%SOURCE_CONFIG%;Backend" ^
  --add-data "%CD%\%SOURCE_VERSION%;Backend" ^
  --collect-all customtkinter ^
  --collect-all pypdfium2 ^
  "%SOURCE_ENTRY%"
if errorlevel 1 goto failed

if not exist "%STAGED_EXE%" (
    echo ERROR: The staged EXE was not created:
    echo   %STAGED_EXE%
    goto failed
)
if not exist "%STAGED_DIR%\_internal\_tcl_data" if not exist "%STAGED_DIR%\_internal\tcl_data" (
    echo ERROR: The staged application is missing Tcl runtime data.
    goto failed
)
if not exist "%STAGED_DIR%\_internal\_tk_data" if not exist "%STAGED_DIR%\_internal\tk_data" (
    echo ERROR: The staged application is missing Tk runtime data.
    goto failed
)
dir /S /B "%STAGED_DIR%\_internal\pdfium.dll" >NUL 2>NUL
if errorlevel 1 (
    echo ERROR: The staged application is missing pdfium.dll.
    goto failed
)

if exist "%STAGED_DIR%\Assets" rmdir /S /Q "%STAGED_DIR%\Assets"
mkdir "%STAGED_DIR%\Assets"
copy /Y "%ICON_FILE%" "%STAGED_DIR%\Assets\ShowersProgrammer.ico" >NUL
copy /Y "%PNG_FILE%" "%STAGED_DIR%\Assets\ShowersProgrammer.png" >NUL
if errorlevel 1 goto failed

echo Writing staged update metadata...
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import hashlib,json,pathlib,sys; app=pathlib.Path(sys.argv[1]); version=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')); exe=app/'Shower Programmer.exe'; source=pathlib.Path(sys.argv[3]); sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest().lower(); data={'sha':sys.argv[4],'version':version['version'],'release_name':version['release_name'],'exe_sha256':sha(exe),'gui_sha256':sha(source),'gui_version':version['marker'],'built_at':__import__('datetime').datetime.now().astimezone().isoformat(),'method':'build'}; (app/'.shower_update.json').write_text(json.dumps(data,separators=(',',':'))+'\n',encoding='utf-8')" "%STAGED_DIR%" "%SOURCE_VERSION%" "%SOURCE_ENTRY%" "%BUILD_SHA%"
if errorlevel 1 goto failed

if not exist "%STAGED_DIR%\Input\Orders" mkdir "%STAGED_DIR%\Input\Orders"
if not exist "%STAGED_DIR%\Input\Process List" mkdir "%STAGED_DIR%\Input\Process List"
if not exist "%STAGED_DIR%\Input\Tools" mkdir "%STAGED_DIR%\Input\Tools"
if not exist "%STAGED_DIR%\Output" mkdir "%STAGED_DIR%\Output"

echo Running packaged EXE self-test...
start "" /wait "%CD%\%STAGED_EXE%" --self-test "%CD%\%PACKAGED_SELF_TEST%"
if errorlevel 1 (
    echo ERROR: The packaged EXE self-test failed.
    if exist "%PACKAGED_SELF_TEST%" type "%PACKAGED_SELF_TEST%"
    goto failed
)
if not exist "%PACKAGED_SELF_TEST%" (
    echo ERROR: The packaged EXE did not create its self-test report.
    goto failed
)
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import json,pathlib; d=json.loads(pathlib.Path(r'%PACKAGED_SELF_TEST%').read_text(encoding='utf-8')); flags=r'%REQUIRED_FLAGS%'.split(','); assert d.get('ok') is True,d; assert d.get('display_version')==r'%APP_VERSION%',d; assert d.get('version')==r'%APP_MARKER%',d; missing=[k for k in flags if d.get(k) is not True]; assert not missing,missing; print('  Packaged EXE self-test passed for '+r'%APP_VERSION%'+'.')"
if errorlevel 1 goto failed

echo Building clean automatic-update package...
if not exist "%UPDATE_RELEASE_DIR%" mkdir "%UPDATE_RELEASE_DIR%"
"%PYTHON_EXE%" %PYTHON_ARGS% "%SOURCE_PACKAGE_BUILDER%" ^
  --app-dir "%STAGED_DIR%" ^
  --zip "%UPDATE_ZIP%" ^
  --metadata "%UPDATE_METADATA%" ^
  --version-file "%SOURCE_VERSION%" ^
  --changelog "%SOURCE_CHANGELOG%" ^
  --commit "%BUILD_SHA%"
if errorlevel 1 goto failed

echo Deploying runtime while preserving local data...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$stage=[IO.Path]::GetFullPath('%STAGED_DIR%');" ^
  "$final=[IO.Path]::GetFullPath('%FINAL_DIR%');" ^
  "$backup=[IO.Path]::GetFullPath('build\deploy_backup');" ^
  "$names=@('_internal','Assets','Shower Programmer.exe','.shower_update.json');" ^
  "New-Item -ItemType Directory -Force -Path $final | Out-Null;" ^
  "if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Recurse -Force};" ^
  "New-Item -ItemType Directory -Force -Path $backup | Out-Null;" ^
  "try {" ^
  " foreach($name in $names){$old=Join-Path $final $name; if(Test-Path -LiteralPath $old){Move-Item -LiteralPath $old -Destination (Join-Path $backup $name) -Force}};" ^
  " foreach($name in $names){$src=Join-Path $stage $name; $dst=Join-Path $final $name; if(Test-Path -LiteralPath $src){Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force}};" ^
  " Remove-Item -LiteralPath $backup -Recurse -Force;" ^
  "} catch {" ^
  " foreach($name in $names){$dst=Join-Path $final $name; if(Test-Path -LiteralPath $dst){Remove-Item -LiteralPath $dst -Recurse -Force}};" ^
  " foreach($name in $names){$old=Join-Path $backup $name; if(Test-Path -LiteralPath $old){Move-Item -LiteralPath $old -Destination (Join-Path $final $name) -Force}};" ^
  " throw" ^
  "}"
if errorlevel 1 (
    echo ERROR: Runtime deployment failed. The previous runtime was restored.
    goto failed
)

if not exist "%FINAL_DIR%\Input\Orders" mkdir "%FINAL_DIR%\Input\Orders"
if not exist "%FINAL_DIR%\Input\Process List" mkdir "%FINAL_DIR%\Input\Process List"
if not exist "%FINAL_DIR%\Input\Tools" mkdir "%FINAL_DIR%\Input\Tools"
if not exist "%FINAL_DIR%\Output" mkdir "%FINAL_DIR%\Output"

echo.
echo ========================================
echo   BUILD COMPLETE - %APP_VERSION%
echo ========================================
echo.
echo Application:
echo   %CD%\%FINAL_DIR%\%APP_NAME%.exe
echo.
echo Update package:
echo   %CD%\%UPDATE_ZIP%
echo   %CD%\%UPDATE_METADATA%
echo.
echo Source self-test:
echo   %CD%\%SOURCE_SELF_TEST%
echo Packaged self-test:
echo   %CD%\%PACKAGED_SELF_TEST%
echo.
goto success

:cancelled
echo.
echo Build cancelled. No files were changed.
exit /b 1

:failed
echo.
echo ========================================
echo   BUILD FAILED
 echo ========================================
echo Review the first ERROR line above. The existing packaged runtime was not intentionally replaced unless deployment completed.
if not defined NO_PAUSE pause
exit /b 1

:success
if not defined NO_PAUSE pause
exit /b 0
