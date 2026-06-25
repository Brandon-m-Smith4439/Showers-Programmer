$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$IconPath = Join-Path $Root 'Assets\ShowersProgrammer.ico'
$IconScript = Join-Path $Root 'Backend\create_app_icon.py'
$LauncherSource = Join-Path $Root 'Backend\ShowerProgrammerLauncher.cs'
$OutputExe = Join-Path $Root 'Shower Programmer.exe'

$BundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $BundledPython) {
    $Python = $BundledPython
} else {
    $Python = 'py'
}

if (-not (Test-Path -LiteralPath $IconPath)) {
    if ($Python -eq 'py') {
        & py -3 $IconScript
    } else {
        & $Python $IconScript
    }
}

$CscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework64\v3.5\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v3.5\csc.exe"
)
$Csc = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Csc) {
    throw 'Could not find the Microsoft C# compiler included with Windows/.NET Framework.'
}

& $Csc /nologo /target:winexe /out:$OutputExe /win32icon:$IconPath /reference:System.Windows.Forms.dll $LauncherSource
if (-not (Test-Path -LiteralPath $OutputExe)) {
    throw "Expected launcher was not created: $OutputExe"
}

Write-Host "Built $OutputExe"
