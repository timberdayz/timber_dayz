param(
    [Parameter(Mandatory = $true)]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$WorkTag,

    [Parameter(Mandatory = $true)]
    [string]$Step,

    [Parameter(Mandatory = $true)]
    [string]$Name,

    [string]$Ref,

    [string]$Ext = "png"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Helper = Join-Path $PSScriptRoot "pwcli_workflow.py"
$Pwcli = Join-Path $PSScriptRoot "pwcli.ps1"

$WorkDir = python $Helper work-dir --repo-root $RepoRoot --platform $Platform --work-tag $WorkTag
$SessionName = python $Helper session-name --platform $Platform --work-tag $WorkTag
$TargetPath = python $Helper screenshot-path --work-dir $WorkDir --step $Step --name $Name --ext $Ext

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$Before = @{}
Get-ChildItem -Path $WorkDir -File -Include *.png,*.jpg,*.jpeg -ErrorAction SilentlyContinue | ForEach-Object {
    $Before[$_.FullName] = $true
}

Push-Location $WorkDir
try {
    if ($Ref) {
        $Output = (& $Pwcli --session $SessionName screenshot $Ref 2>&1 | Out-String)
    } else {
        $Output = (& $Pwcli --session $SessionName screenshot 2>&1 | Out-String)
    }
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($ExitCode -ne 0) {
    Write-Error $Output
    exit $ExitCode
}

$Created = Get-ChildItem -Path $WorkDir -File -Include *.png,*.jpg,*.jpeg -ErrorAction SilentlyContinue |
    Where-Object { -not $Before.ContainsKey($_.FullName) } |
    Sort-Object LastWriteTime -Descending

if (-not $Created) {
    Write-Error "No screenshot artifact was created"
    exit 1
}

$Source = $Created[0].FullName
Move-Item -Force -Path $Source -Destination $TargetPath
Write-Output $TargetPath
