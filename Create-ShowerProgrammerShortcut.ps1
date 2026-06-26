$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ShortcutPath = Join-Path $Root 'Shower Programmer.lnk'
$TargetPath = Join-Path $Root 'GUI.bat'
$IconPath = Join-Path $Root 'Assets\ShowersProgrammer.ico'
$DesktopShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Shower Programmer.lnk'
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Shower Programmer'
$StartMenuShortcutPath = Join-Path $StartMenuDir 'Shower Programmer.lnk'
$TaskbarDir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
$TaskbarShortcutPath = Join-Path $TaskbarDir 'Shower Programmer.lnk'

if (-not (Test-Path -LiteralPath $TargetPath)) {
    throw "Could not find launcher batch file: $TargetPath"
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

try {
    New-ShowerProgrammerShortcut -Path $TaskbarShortcutPath
    Write-Host "Copied taskbar shortcut to $TaskbarShortcutPath"
} catch {
    Write-Warning "Could not create the taskbar shortcut copy: $($_.Exception.Message)"
}

Write-Host "Created $ShortcutPath"
Write-Host "Created $DesktopShortcutPath"
Write-Host "Created $StartMenuShortcutPath"
Write-Host "If Windows does not show it on the taskbar immediately, right-click the Start Menu shortcut and choose Pin to taskbar."
