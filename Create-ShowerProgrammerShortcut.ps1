param(
    [string]$Root = $PSScriptRoot,
    [string]$DesktopPath = [Environment]::GetFolderPath('Desktop'),
    [string]$StartMenuPath = (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Shower Programmer')
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$ShortcutPath = Join-Path $Root 'Shower Programmer.lnk'
$FastExePath = Join-Path $Root 'Shower Programmer.exe'
if (-not (Test-Path -LiteralPath $FastExePath)) { $FastExePath = Join-Path $Root 'Shower Programmer\Shower Programmer.exe' }
$BatchPath = Join-Path $Root 'GUI.bat'
$TargetPath = if (Test-Path -LiteralPath $FastExePath) { $FastExePath } else { $BatchPath }
$Arguments = ''
$LocalPython = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $FastExePath) -and (Test-Path -LiteralPath $LocalPython)) {
    $TargetPath = $LocalPython
    $Arguments = '"' + (Join-Path $Root 'Backend\shower_programmer_v4.py') + '"'
}
$IconPath = Join-Path $Root 'Assets\ShowersProgrammer.ico'
$DesktopShortcutPath = Join-Path $DesktopPath 'Shower Programmer.lnk'
$StartMenuDir = $StartMenuPath
$StartMenuShortcutPath = Join-Path $StartMenuDir 'Shower Programmer.lnk'

if (-not (Test-Path -LiteralPath $TargetPath)) {
    throw "Could not find Shower Programmer launcher: $TargetPath"
}

function New-ShowerProgrammerShortcut {
    param(
        [Parameter(Mandatory=$true)][string]$Path
    )
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $TargetPath
    $Shortcut.Arguments = $Arguments
    $Shortcut.WorkingDirectory = $Root
    $Shortcut.Description = 'Launch Shower Programmer'
    if (Test-Path -LiteralPath $IconPath) {
        $Shortcut.IconLocation = "$IconPath,0"
    }
    $Shortcut.Save()
    try {
        Unblock-File -LiteralPath $Path -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Created the shortcut, but Windows would not unblock it automatically: $($_.Exception.Message)"
    }
}

New-ShowerProgrammerShortcut -Path $ShortcutPath
New-ShowerProgrammerShortcut -Path $DesktopShortcutPath
New-ShowerProgrammerShortcut -Path $StartMenuShortcutPath

Write-Host "Created $ShortcutPath"
Write-Host "Created $DesktopShortcutPath"
Write-Host "Created $StartMenuShortcutPath"
Write-Host 'Taskbar pinning requires your approval: launch the app, right-click its taskbar icon, and choose Pin to taskbar.'
