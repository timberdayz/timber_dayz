param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag,

    [Parameter(Mandatory = $true)]
    [string]$Step,

    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [ValidateSet("before", "after")]
    [string]$Phase
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag
$SessionName = python $Helper session-name --platform $Platform --work-tag $WorkTag
$OutputPath = python $Helper snapshot-path --work-dir $WorkDir --step $Step --name $Name --phase $Phase

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

Push-Location $WorkDir
try {
    $SnapshotOutput = (& $Pwcli --session $SessionName snapshot 2>&1 | Out-String)
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($ExitCode -ne 0) {
    Write-Error $SnapshotOutput
    exit $ExitCode
}

[System.IO.File]::WriteAllText($OutputPath, $SnapshotOutput, [System.Text.UTF8Encoding]::new($false))
Write-Output $OutputPath
