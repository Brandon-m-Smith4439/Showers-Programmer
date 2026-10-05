param(
    [string]$AppRoot = $PSScriptRoot,
    [switch]$NoLaunch,
    [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($AppRoot)
$Exe = Join-Path $Root 'Shower Programmer.exe'
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    $Exe = Join-Path $Root 'Shower Programmer\Shower Programmer.exe'
}
$Packaged = Test-Path -LiteralPath $Exe -PathType Leaf
$Runtime = if ($Packaged) { Split-Path -Parent $Exe } else { $Root }
$Script = Join-Path $Root 'Backend\shower_programmer_v4.py'
if ($Packaged -and -not (Test-Path -LiteralPath (Join-Path $Runtime '_internal') -PathType Container)) {
    throw 'The EXE needs its complete one-folder package, including _internal. Extract/copy the whole application folder first.'
}
if (-not $Packaged -and -not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    throw 'Could not find the one-folder EXE or Backend\shower_programmer_v4.py next to setup.'
}
foreach ($Relative in @('Input\Orders','Input\Process List','Input\Tools','Output\Runs','Output\Updates','Diagnostics')) {
    New-Item -ItemType Directory -Path (Join-Path $Runtime $Relative) -Force | Out-Null
}

if ($Packaged) {
    Write-Host 'Using the packaged application. Python is not required for this installation.'
    $Target = $Exe
    $Arguments = ''
} else {
    $Requirements = Join-Path $Root 'requirements.txt'
    if (-not (Test-Path -LiteralPath $Requirements)) { throw 'Missing requirements.txt. Copy the complete source folder.' }
    $Venv = Join-Path $Root '.venv'
    $Python = Join-Path $Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) {
        $Probe = "import sys,tkinter; assert sys.version_info >= (3,10), 'Python 3.10 or newer is required'; print(sys.executable)"
        $BasePython = $null
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $Output = & py -3 -c $Probe
            if ($LASTEXITCODE -eq 0) { $BasePython = [string](@($Output)[-1]) }
        }
        if (-not $BasePython -and (Get-Command python -ErrorAction SilentlyContinue)) {
            $Output = & python -c $Probe
            if ($LASTEXITCODE -eq 0) { $BasePython = [string](@($Output)[-1]) }
        }
        if (-not $BasePython) { throw 'Install Python 3.10 or newer with Tcl/Tk and pip, then run setup again. No administrator install is required.' }
        Write-Host 'Creating a local Python environment...'
        & $BasePython -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment. Check Python installation and folder permissions.' }
    }
    Write-Host 'Checking/installing Python dependencies locally (Internet access may be needed)...'
    & $Python -m pip install --disable-pip-version-check -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet/proxy access and rerun setup.' }
    & $Python -c "import tkinter, customtkinter, PIL, pypdf, pypdfium2, openpyxl, reportlab; print('Application dependencies verified.')"
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency verification failed.' }
    $Target = Join-Path $Venv 'Scripts\pythonw.exe'
    $Arguments = '"' + $Script + '"'
}

if (-not $NoShortcuts) {
    $ShortcutScript = Join-Path $PSScriptRoot 'Create-ShowerProgrammerShortcut.ps1'
    & $ShortcutScript -Root $Root
}
Write-Host "Local inputs and output folders are ready: $Runtime"
Write-Host 'Shared I: drive locations can be changed in Settings > Folder Setup.'
Write-Host 'Optional Excel/AutoCAD integrations still require those applications when used.'
if (-not $NoLaunch) {
    if ($Arguments) {
        Start-Process -FilePath $Target -ArgumentList $Arguments -WorkingDirectory $Root -WindowStyle Hidden
    } else {
        Start-Process -FilePath $Target -WorkingDirectory $Runtime -WindowStyle Hidden
    }
}
