param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [string]$Ref,

    [string]$Ext = "png"
)

$ErrorActionPreference = "Stop"

$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"

$CapturePaths = python $Helper capture-paths --work-dir (Get-Location).Path --name $Name --ext $Ext | ConvertFrom-Json
$SnapshotPath = $CapturePaths.snapshot_path
$ScreenshotPath = $CapturePaths.screenshot_path

$SnapshotOutput = (& $Pwcli snapshot 2>&1 | Out-String)
$SnapshotExitCode = $LASTEXITCODE

if ($SnapshotExitCode -ne 0) {
    Write-Error $SnapshotOutput
    exit $SnapshotExitCode
}

[System.IO.File]::WriteAllText($SnapshotPath, $SnapshotOutput, [System.Text.UTF8Encoding]::new($false))

$Before = @{}
Get-ChildItem -File | Where-Object { $_.Extension -in @(".png", ".jpg", ".jpeg") } | ForEach-Object {
    $Before[$_.FullName] = $true
}

if ($Ref) {
    $ScreenshotOutput = (& $Pwcli screenshot $Ref 2>&1 | Out-String)
} else {
    $ScreenshotOutput = (& $Pwcli screenshot 2>&1 | Out-String)
}
$ScreenshotExitCode = $LASTEXITCODE

if ($ScreenshotExitCode -ne 0) {
    Write-Error $ScreenshotOutput
    exit $ScreenshotExitCode
}

$Created = Get-ChildItem -File |
    Where-Object { $_.Extension -in @(".png", ".jpg", ".jpeg") -and -not $Before.ContainsKey($_.FullName) } |
    Sort-Object LastWriteTime -Descending

if (-not $Created) {
    Write-Error "No screenshot artifact was created."
    exit 1
}

Move-Item -Force -Path $Created[0].FullName -Destination $ScreenshotPath

[pscustomobject]@{
    SnapshotPath   = (Resolve-Path $SnapshotPath).Path
    ScreenshotPath = (Resolve-Path $ScreenshotPath).Path
}
