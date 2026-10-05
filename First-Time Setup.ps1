param(
    [string]$AppRoot = $PSScriptRoot,
    [switch]$NoLaunch,
    [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($AppRoot)
function Get-SetupMetadataVersion($Metadata) {
    if ($Metadata.version_number) { return [int]$Metadata.version_number }
    if ([string]$Metadata.version -match '^(?:Version\s+)?(\d+)\.(\d{2})$') {
        return ([int]$Matches[1] * 100 + [int]$Matches[2])
    }
    return $null
}

function Get-SetupPackageVersion([string]$Folder) {
    $metadata = Join-Path $Folder '.shower_update.json'
    if (Test-Path -LiteralPath $metadata -PathType Leaf) {
        return (Get-SetupMetadataVersion (Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json))
    }
    return $null
}

function Get-SetupSourceFingerprint([string]$Folder) {
    $files = @()
    foreach ($relative in @('Backend','Assets')) {
        $directory = Join-Path $Folder $relative
        if (Test-Path -LiteralPath $directory) {
            $files += @(Get-ChildItem -LiteralPath $directory -Recurse -File |
                Where-Object { $_.Extension -in @('.py','.json','.txt','.png','.ico') })
        }
    }
    $requirements = Join-Path $Folder 'requirements.txt'
    if (Test-Path -LiteralPath $requirements) { $files += Get-Item -LiteralPath $requirements }
    $paths = [string[]]@($files | ForEach-Object { $_.FullName })
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    $lines = foreach ($path in $paths) {
        $relative = $path.Substring($Folder.Length+1).Replace('\','/')
        $relative + '=' + (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() + "`n"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join ''))))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Ensure-FirstTimeExecutable([string]$Folder) {
    $repair = Join-Path $PSScriptRoot 'Repair Programmer.ps1'
    if (-not (Test-Path -LiteralPath $repair -PathType Leaf)) {
        throw 'Missing Repair Programmer.ps1. Keep the complete setup/package folder together.'
    }
    . $repair
    $Folder = Assert-SafeRepairPath $Folder
    $sourceVersion = Join-Path $Folder 'Backend\version.json'
    $expected = if (Test-Path -LiteralPath $sourceVersion) {
        (Get-Content -LiteralPath $sourceVersion -Raw | ConvertFrom-Json).version_number
    } else { $null }
    $fingerprint = if (Test-Path -LiteralPath (Join-Path $Folder 'Backend\shower_programmer_v4.py')) {
        Get-SetupSourceFingerprint $Folder
    } else { $null }
    $existing = $null
    try { $existing = Resolve-ProgrammerPackage $Folder } catch { }
    $existingMatches = $existing -and (-not $expected -or (Get-SetupPackageVersion $existing) -eq $expected)
    if ($existingMatches -and $fingerprint) {
        $metadata = Get-Content -LiteralPath (Join-Path $existing '.shower_update.json') -Raw | ConvertFrom-Json
        $existingMatches = $metadata.source_sha256 -eq $fingerprint
    }
    if ($existingMatches) {
        return (Join-Path $existing 'Shower Programmer.exe')
    }

    $archives = @()
    foreach ($relative in @('release','Recovery','Recover')) {
        $directory = Join-Path $Folder $relative
        if (Test-Path -LiteralPath $directory -PathType Container) {
            $archives += @(Get-ChildItem -LiteralPath $directory -Filter '*.zip' -File -Recurse |
                Sort-Object LastWriteTime -Descending)
        }
    }
    $allowed = @('Shower Programmer.exe','_internal','Assets','.shower_update.json',
        'First-Time Setup.bat','First-Time Setup.ps1','Create-ShowerProgrammerShortcut.ps1',
        'Repair Programmer.bat','Repair Programmer.ps1')
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($archive in $archives) {
        Assert-NoRuntimeLinks $archive.FullName
        $zip = [IO.Compression.ZipFile]::OpenRead($archive.FullName)
        $stage = $null
        try {
            $markers = @($zip.Entries | Where-Object { $_.FullName.Replace('\','/').Split('/')[-1] -eq '.shower_update.json' })
            if ($markers.Count -ne 1) { continue }
            $reader = New-Object IO.StreamReader($markers[0].Open())
            try { $metadata = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            $packageVersion = Get-SetupMetadataVersion $metadata
            if (-not $packageVersion -or ($expected -and $packageVersion -ne $expected) -or
                ($fingerprint -and $metadata.source_sha256 -ne $fingerprint)) { continue }
            $prefix = $markers[0].FullName.Replace('\','/').Substring(0, $markers[0].FullName.Length - '.shower_update.json'.Length)
            $stage = Assert-SafeRepairPath (Join-Path ([IO.Path]::GetTempPath()) ('SP-Setup-'+[Guid]::NewGuid().ToString('N')))
            New-Item -ItemType Directory -Path $stage | Out-Null
            $seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
            $size = 0L
            foreach ($entry in $zip.Entries) {
                $name = $entry.FullName.Replace('\','/')
                if (-not $name.StartsWith($prefix, [StringComparison]::Ordinal)) { continue }
                $name = $name.Substring($prefix.Length)
                if (-not $name -or $name.EndsWith('/')) { continue }
                if ($name.StartsWith('/') -or $name.Contains(':') -or @($name.Split('/') | Where-Object { $_ -in @('..','.') }).Count) {
                    throw 'Unsafe path in the setup archive. Use a complete trusted Windows package.'
                }
                if ($name.Split('/')[0] -notin $allowed) { continue }
                if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Linked archive entries are not allowed.' }
                if (-not $seen.Add($name)) { throw 'Duplicate runtime paths in the setup archive.' }
                $size += $entry.Length
                if ($size -gt 2GB) { throw 'The setup package exceeds the runtime size limit.' }
                $destination = [IO.Path]::GetFullPath((Join-Path $stage $name))
                if (-not $destination.StartsWith($stage+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path escapes staging.' }
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $false)
            }
            Assert-ProgrammerBundle $stage
            Write-Host "Checking recovered package: $($archive.Name)"
            Test-ProgrammerRuntime $stage (Join-Path $stage 'setup-self-test.json')
            if ($existing) {
                Install-ProgrammerRuntime -InstallDir $existing -PackageDir $stage | Out-Host
                return (Join-Path $existing 'Shower Programmer.exe')
            }
            $target = Assert-SafeRepairPath (Join-Path $Folder 'Shower Programmer')
            foreach ($name in $allowed) {
                if (Test-Path -LiteralPath (Join-Path $target $name)) {
                    throw "An incomplete runtime already exists at $target. Use Repair / Manual Update before setup. Your data has not been changed."
                }
            }
            New-Item -ItemType Directory -Path $target -Force | Out-Null
            foreach ($name in $allowed) {
                if (Test-Path -LiteralPath (Join-Path $stage $name)) {
                    Move-Item -LiteralPath (Join-Path $stage $name) -Destination (Join-Path $target $name)
                }
            }
            return (Join-Path $target 'Shower Programmer.exe')
        } finally {
            $zip.Dispose()
            if ($stage -and (Test-Path -LiteralPath $stage)) {
                Assert-SafeRepairPath $stage | Out-Null
                Assert-NoRuntimeLinks $stage
                Remove-Item -LiteralPath $stage -Recurse -Force
            }
        }
    }
    $builder = Join-Path $Folder 'Rebuild Shower Programmer EXE.bat'
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'Backend\shower_programmer_v4.py')) -or
        -not (Test-Path -LiteralPath $builder)) {
        throw 'No complete current Windows package or buildable source was found. Extract the full Windows application ZIP, not just the EXE.'
    }
    $Requirements = Join-Path $Folder 'requirements.txt'
    if (-not (Test-Path -LiteralPath $Requirements)) { throw 'Missing requirements.txt. Copy the complete source folder.' }
    $Venv = Join-Path $Folder '.venv'
    $Python = Join-Path $Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) {
        $Probe = "import sys,tkinter; assert sys.version_info >= (3,10), 'Python 3.10 or newer is required'; print(sys.executable)"
        $BasePython = $null
        foreach ($command in @('py','python')) {
            if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { continue }
            $Output = if ($command -eq 'py') { & py -3 -c $Probe } else { & python -c $Probe }
            if ($LASTEXITCODE -eq 0) { $BasePython = [string](@($Output)[-1]); break }
        }
        if (-not $BasePython) { throw 'Install Python 3.10 or newer with Tcl/Tk and pip, then run setup again.' }
        Write-Host 'Creating a local build environment...'
        & $BasePython -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
    }
    Write-Host 'Installing local build dependencies (Internet access may be needed)...'
    & $Python -m pip install --disable-pip-version-check -r $Requirements pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed. Check Internet/proxy access and retry.' }
    Write-Host 'Building the current one-folder EXE. This first-time step can take several minutes...'
    & $builder /nopause | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'The EXE build failed. Review the build message; no Python GUI fallback was launched.' }
    $built = Resolve-ProgrammerPackage $Folder
    if ($expected -and (Get-SetupPackageVersion $built) -ne $expected) { throw 'Built EXE metadata does not match the source version.' }
    return (Join-Path $built 'Shower Programmer.exe')
}

if ($MyInvocation.InvocationName -ne '.') {
$Exe = Ensure-FirstTimeExecutable $Root
$Runtime = Split-Path -Parent $Exe
foreach ($Relative in @('Input\Orders','Input\Process List','Input\Tools','Output\Runs','Output\Updates','Diagnostics')) {
    New-Item -ItemType Directory -Path (Join-Path $Runtime $Relative) -Force | Out-Null
}
$Target = $Exe
Write-Host 'Using the one-folder EXE. Python is not required to run the installed application.'

if (-not $NoShortcuts) {
    $ShortcutScript = Join-Path $PSScriptRoot 'Create-ShowerProgrammerShortcut.ps1'
    & $ShortcutScript -Root $Runtime
}
Write-Host "Local inputs and output folders are ready: $Runtime"
Write-Host 'Shared I: drive locations can be changed in Settings > Folder Setup.'
Write-Host 'Optional Excel/AutoCAD integrations still require those applications when used.'
if (-not $NoLaunch) {
    Start-Process -FilePath $Target -WorkingDirectory $Runtime -WindowStyle Hidden
}
}
