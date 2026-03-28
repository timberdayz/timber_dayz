param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag,

    [Parameter(Mandatory = $true)]
    [string]$Url
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag
$SessionName = python $Helper session-name --platform $Platform --work-tag $WorkTag

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

& $Pwcli --session $SessionName open $Url
exit $LASTEXITCODE
