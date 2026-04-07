param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [string]$Ref,

    [string]$Ext = "png",

    [string]$Session = $env:PLAYWRIGHT_CLI_SESSION
)

$ErrorActionPreference = "Stop"

$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"
$ResolvedSession = $null
if (-not [string]::IsNullOrWhiteSpace($Session)) {
    $ResolvedSession = $Session.Trim()
}

function Invoke-PwcliCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $pwcliArgs = @()
    if ($ResolvedSession) {
        $pwcliArgs += "-s=$ResolvedSession"
    }
    $pwcliArgs += $Arguments

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = (& $Pwcli @pwcliArgs 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    [pscustomobject]@{
        Output   = $output
        ExitCode = $exitCode
    }
}

$CapturePaths = python $Helper capture-paths --work-dir (Get-Location).Path --name $Name --ext $Ext | ConvertFrom-Json
$SnapshotPath = $CapturePaths.snapshot_path
$ScreenshotPath = $CapturePaths.screenshot_path

$SnapshotResult = Invoke-PwcliCapture -Arguments @("snapshot")
$SnapshotOutput = $SnapshotResult.Output
$SnapshotExitCode = $SnapshotResult.ExitCode

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
    $ScreenshotResult = Invoke-PwcliCapture -Arguments @("screenshot", $Ref)
} else {
    $ScreenshotResult = Invoke-PwcliCapture -Arguments @("screenshot")
}
$ScreenshotOutput = $ScreenshotResult.Output
$ScreenshotExitCode = $ScreenshotResult.ExitCode

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
