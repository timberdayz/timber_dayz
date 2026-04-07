param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag,

    [Parameter(Mandatory = $true)]
    [string]$Step,

    [Parameter(Mandatory = $true)]
    [string]$Text
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag
$NotePath = python $Helper note-path --work-dir $WorkDir --step $Step

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
[System.IO.File]::WriteAllText($NotePath, $Text + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
Write-Output $NotePath
