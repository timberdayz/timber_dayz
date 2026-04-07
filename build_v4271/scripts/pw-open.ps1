param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag,

    [Parameter(Mandatory = $true)]
    [string]$Url,

    [string]$AccountId
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"
$StateFile = Join-Path $RepoRoot "output\playwright\state\$($Platform.ToLower()).json"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag
$SessionName = python $Helper session-name --platform $Platform --work-tag $WorkTag

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

if ($AccountId) {
    & $Pwcli --session $SessionName open $Url --account-id $AccountId
} else {
    & $Pwcli --session $SessionName open $Url
}
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    exit $ExitCode
}

if (-not $AccountId -and (Test-Path $StateFile)) {
    & $Pwcli --session $SessionName state-load $StateFile
    $StateExitCode = $LASTEXITCODE

    if ($StateExitCode -eq 0) {
        & $Pwcli --session $SessionName reload
        $null = $LASTEXITCODE
    } else {
        Write-Warning "Failed to load pwcli state from $StateFile. Continuing with a fresh browser state."
    }
}

exit 0
