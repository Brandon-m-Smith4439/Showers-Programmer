param([string]$InstallDir, [string]$PackageDir = $PSScriptRoot, [switch]$ConfirmRepair)
$ErrorActionPreference = 'Stop'

function Assert-SafeRepairPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\')) { throw 'Choose the application folder, not a drive root.' }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked folders are not safe repair targets: $cursor. Choose the actual local folder." }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}

function Assert-NoRuntimeLinks([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $pending = New-Object 'Collections.Generic.Stack[IO.FileSystemInfo]'
    $pending.Push((Get-Item -LiteralPath $Path -Force))
    while ($pending.Count) {
        $item = $pending.Pop()
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked runtime item is not supported: $($item.FullName)" }
        if ($item -is [IO.DirectoryInfo]) {
            foreach ($child in $item.GetFileSystemInfos()) { $pending.Push($child) }
        }
    }
}

function Assert-ProgrammerBundle([string]$Folder) {
    foreach ($relative in @('Shower Programmer.exe', 'Assets\ShowersProgrammer.ico', '_internal\pypdfium2_raw\pdfium.dll')) {
        $path = Join-Path $Folder $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) { throw "Incomplete program package: missing $relative. Extract the entire Windows ZIP." }
    }
    foreach ($pair in @(@('_tcl_data','tcl_data','init.tcl'), @('_tk_data','tk_data','tk.tcl'))) {
        $a = Join-Path $Folder ('_internal\'+$pair[0]+'\'+$pair[2])
        $b = Join-Path $Folder ('_internal\'+$pair[1]+'\'+$pair[2])
        if (-not (Test-Path -LiteralPath $a -PathType Leaf) -and -not (Test-Path -LiteralPath $b -PathType Leaf)) { throw "Incomplete program package: missing $($pair[2])." }
    }
}

function Assert-ProgrammerClosed([string]$Folder) {
    $exe = Join-Path $Folder 'Shower Programmer.exe'
    $running = @(Get-CimInstance Win32_Process -Filter "Name = 'Shower Programmer.exe'" | Where-Object { -not $_.ExecutablePath -or [IO.Path]::GetFullPath($_.ExecutablePath) -eq $exe })
    if ($running.Count) { throw 'The existing Shower Programmer is still running. Close it (or end its frozen process in Task Manager), then retry. No process was forcibly closed.' }
}

function Test-ProgrammerRuntime([string]$Folder, [string]$Report) {
    # Self-tests create nested fixtures. Keep those out of long installation/rollback paths.
    $testRoot = Assert-SafeRepairPath (Join-Path ([IO.Path]::GetTempPath()) ('SP-Check-'+[Guid]::NewGuid().ToString('N').Substring(0,8)))
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $testReport = Join-Path $testRoot 'result.json'
    try {
        $process = Start-Process -FilePath (Join-Path $Folder 'Shower Programmer.exe') -ArgumentList ('--self-test "'+$testReport+'"') -WorkingDirectory $Folder -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(90000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            throw 'The new runtime self-test timed out. The repair was stopped.'
        }
        $process.Refresh()
        if (Test-Path -LiteralPath $testReport) { Copy-Item -LiteralPath $testReport -Destination $Report -Force }
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Report)) { throw "The new runtime did not pass its self-test. Details: $Report" }
        $data = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
        if (-not $data.ok) { throw 'The new runtime self-test reported a failure.' }
        $metadata = Join-Path $Folder '.shower_update.json'
        if (Test-Path -LiteralPath $metadata) {
            $expected = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
            if ($expected.version -and $expected.version -ne $data.display_version) { throw 'The EXE version does not match the package metadata.' }
            $hash = (Get-FileHash -LiteralPath (Join-Path $Folder 'Shower Programmer.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($expected.exe_sha256 -and $expected.exe_sha256 -ne $hash) { throw 'The EXE does not match its package checksum.' }
        }
    } finally {
        Assert-SafeRepairPath $testRoot | Out-Null
        Assert-NoRuntimeLinks $testRoot
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}

function Install-ProgrammerRuntime {
    param([Parameter(Mandatory=$true)][string]$InstallDir, [Parameter(Mandatory=$true)][string]$PackageDir,
          [scriptblock]$Validator = {param($folder,$report) Test-ProgrammerRuntime $folder $report},
          [scriptblock]$Progress = {param($percent,$message) Write-Host "$percent% $message"})
    $target = Assert-SafeRepairPath $InstallDir
    $source = Assert-SafeRepairPath $PackageDir
    if ($target -eq $source -or $source.StartsWith($target+'\', [StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith($source+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'The replacement package must be in a separate folder, outside the existing installation.' }
    if (-not (Test-Path -LiteralPath (Join-Path $target 'Shower Programmer.exe') -PathType Leaf)) { throw 'This folder does not contain an existing Shower Programmer.exe.' }
    Assert-ProgrammerBundle $source
    Assert-ProgrammerClosed $target
    $allowed = @('Shower Programmer.exe','_internal','Assets','.shower_update.json','First-Time Setup.bat','First-Time Setup.ps1','Create-ShowerProgrammerShortcut.ps1','Repair Programmer.bat','Repair Programmer.ps1')
    $names = @($allowed | Where-Object { Test-Path -LiteralPath (Join-Path $source $_) })
    foreach ($name in $names) {
        Assert-NoRuntimeLinks (Join-Path $source $name)
        Assert-NoRuntimeLinks (Join-Path $target $name)
    }
    $id = [DateTime]::Now.ToString('yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
    $backup = Assert-SafeRepairPath (Join-Path $target ('Rollback\ManualUpdate-'+$id))
    $stage = Assert-SafeRepairPath (Join-Path $target ('.__sp_new_manual_'+$id))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    $log = Join-Path $backup 'repair.log'
    $oldMoved = New-Object 'Collections.Generic.List[string]'
    $newMoved = New-Object 'Collections.Generic.List[string]'
    $keepStage = $false
    try {
        & $Progress 10 'Copying the replacement into local staging...' | Out-Host
        foreach ($name in $names) { Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $stage $name) -Recurse -Force }
        Assert-ProgrammerBundle $stage
        & $Progress 35 'Checking the new EXE before changing the old installation...' | Out-Host
        & $Validator $stage (Join-Path $backup 'staged-self-test.json') | Out-Null
        Assert-ProgrammerClosed $target
        "Starting runtime replacement: $target`r`nReplacement: $source`r`nInput, Output and operator state are not replacement targets." | Set-Content -LiteralPath $log
        & $Progress 55 'Backing up the existing program files...' | Out-Host
        foreach ($name in $names) {
            $old = Join-Path $target $name
            if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination (Join-Path $backup $name); $oldMoved.Add($name) }
        }
        & $Progress 70 'Installing the new program files...' | Out-Host
        foreach ($name in $names) { Move-Item -LiteralPath (Join-Path $stage $name) -Destination (Join-Path $target $name); $newMoved.Add($name) }
        & $Progress 85 'Validating the installed runtime...' | Out-Host
        Assert-ProgrammerBundle $target
        & $Validator $target (Join-Path $backup 'installed-self-test.json') | Out-Null
        Add-Content -LiteralPath $log -Value 'Repair succeeded. Previous program files are retained in this backup.'
        & $Progress 100 'Repair complete. Your input, output and progress folders were preserved.' | Out-Host
        return @{backup=$backup;install=$target;ok=$true}
    } catch {
        $failure = $_
        $rollbackErrors = New-Object 'Collections.Generic.List[string]'
        foreach ($name in $newMoved) {
            try {
                $path = Join-Path $target $name
                Assert-SafeRepairPath $path | Out-Null
                if (Test-Path -LiteralPath $path) { Move-Item -LiteralPath $path -Destination (Join-Path $stage $name) }
            } catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        foreach ($name in $oldMoved) {
            try {
                $destination = Join-Path $target $name
                if (Test-Path -LiteralPath $destination) { throw "Cannot restore over a locked replacement: $name" }
                Move-Item -LiteralPath (Join-Path $backup $name) -Destination $destination
            } catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        if ($rollbackErrors.Count) {
            $keepStage = $true
            $message = "Repair failed: $($failure.Exception.Message). Rollback needs attention. All backups retained in $backup; staging retained in $stage. " + ($rollbackErrors -join '; ')
            Add-Content -LiteralPath $log -Value $message
            throw $message
        }
        Add-Content -LiteralPath $log -Value ("Repair failed; old program files restored. " + $failure.Exception.Message)
        throw $failure
    } finally {
        if (-not $keepStage) {
            Assert-SafeRepairPath $stage | Out-Null
            Assert-NoRuntimeLinks $stage
            if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        }
    }
}

function Show-ProgrammerRepair {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form = New-Object Windows.Forms.Form
    $form.Text = 'Shower Programmer - Repair / Manual Update'
    $form.Size = New-Object Drawing.Size(690,330)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.BackColor = [Drawing.Color]::FromArgb(242,245,250)
    $form.Font = New-Object Drawing.Font('Segoe UI',10)
    $title = New-Object Windows.Forms.Label
    $title.Text = 'Update the program. Keep your work.'
    $title.Font = New-Object Drawing.Font('Segoe UI',16,[Drawing.FontStyle]::Bold)
    $title.SetBounds(20,18,640,34)
    $form.Controls.Add($title)
    $note = New-Object Windows.Forms.Label
    $note.Text = 'Choose the OLD installation. Only program files are replaced; Input, Output, settings and progress stay in place. Close the programmer first.'
    $note.SetBounds(22,60,630,48)
    $form.Controls.Add($note)
    $field = New-Object Windows.Forms.TextBox
    $field.SetBounds(22,116,520,30)
    $form.Controls.Add($field)
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Shower Programmer.lnk'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Shower Programmer\Shower Programmer.lnk'))) {
        if (Test-Path -LiteralPath $path) {
            $exe = $shell.CreateShortcut($path).TargetPath
            if ([IO.Path]::GetFileName($exe) -eq 'Shower Programmer.exe' -and (Split-Path -Parent $exe) -ne $PackageDir) { $field.Text = Split-Path -Parent $exe; break }
        }
    }
    $browse = New-Object Windows.Forms.Button
    $browse.Text = 'Browse...'
    $browse.SetBounds(554,114,100,32)
    $browse.Add_Click({
        $picker = New-Object Windows.Forms.OpenFileDialog
        $picker.Title = 'Select the EXISTING Shower Programmer.exe to update'
        $picker.Filter = 'Shower Programmer|Shower Programmer.exe'
        if ($picker.ShowDialog($form) -eq 'OK') { $field.Text = Split-Path -Parent $picker.FileName }
        $picker.Dispose()
    })
    $form.Controls.Add($browse)
    $status = New-Object Windows.Forms.Label
    $status.Text = 'Replacement package: '+$PackageDir
    $status.SetBounds(22,155,630,42)
    $form.Controls.Add($status)
    $bar = New-Object Windows.Forms.ProgressBar
    $bar.SetBounds(22,205,630,16)
    $form.Controls.Add($bar)
    $repair = New-Object Windows.Forms.Button
    $repair.Text = 'Repair / Update'
    $repair.BackColor = [Drawing.Color]::FromArgb(38,105,201)
    $repair.ForeColor = [Drawing.Color]::White
    $repair.SetBounds(474,237,180,36)
    $repair.Add_Click({
        try {
            Assert-ProgrammerBundle $PackageDir
            $target = Assert-SafeRepairPath $field.Text
            if ([Windows.Forms.MessageBox]::Show($form, "Update the program in:`r`n$target`r`n`r`nInput, Output and existing operator state will not be replaced.", 'Confirm existing installation', 'YesNo', 'Question') -ne 'Yes') { return }
            $repair.Enabled=$false; $browse.Enabled=$false; $field.Enabled=$false; $form.ControlBox=$false
            $result = Install-ProgrammerRuntime -InstallDir $target -PackageDir $PackageDir -Progress {param($p,$message) $bar.Value=$p; $status.Text=$message; $form.Refresh()}
            [Windows.Forms.MessageBox]::Show($form, "Update complete. Your work is preserved.`r`nPrevious program backup:`r`n$($result.backup)", 'Repair complete', 'OK', 'Information') | Out-Null
            $form.Close()
        } catch {
            $status.Text='Repair stopped. Review the error and retry.'
            [Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Repair stopped', 'OK', 'Error') | Out-Null
        } finally { $repair.Enabled=$true; $browse.Enabled=$true; $field.Enabled=$true; $form.ControlBox=$true }
    })
    $form.Controls.Add($repair)
    $form.ShowDialog() | Out-Null
    $form.Dispose()
}

if ($MyInvocation.InvocationName -ne '.') {
    if ($InstallDir) {
        if (-not $ConfirmRepair) { throw 'Use -ConfirmRepair to explicitly confirm the existing installation.' }
        Install-ProgrammerRuntime -InstallDir $InstallDir -PackageDir $PackageDir
    } else { Show-ProgrammerRepair }
}
