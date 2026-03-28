param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag

python $Helper pack --work-dir $WorkDir --platform $Platform --work-tag $WorkTag
exit $LASTEXITCODE
