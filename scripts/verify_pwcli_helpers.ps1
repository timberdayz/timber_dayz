$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "pwcli_helpers.ps1")

$requiredHelpers = @(
    "pwcli",
    "Open-PwcliMiaoshou",
    "Open-PwcliShopee",
    "Open-PwcliTiktok",
    "Save-PwcliMiaoshouState",
    "Save-PwcliShopeeState",
    "Save-PwcliTiktokState",
    "Show-PwcliPaths",
    "pwsnap",
    "pwnote",
    "pwshot",
    "pwpack",
    "pwcap"
)

$requiredScripts = @(
    "scripts/pwcli.ps1",
    "scripts/pw-open.ps1",
    "scripts/pw-step.ps1",
    "scripts/pw-note.ps1",
    "scripts/pw-shot.ps1",
    "scripts/pw-pack.ps1",
    "scripts/pw-cap.ps1",
    "scripts/pwcli_helpers.ps1",
    "scripts/pwcli_native.py",
    "scripts/pwcli_workflow.py"
)

$missingHelpers = @()
foreach ($helper in $requiredHelpers) {
    if (-not (Get-Command $helper -ErrorAction SilentlyContinue)) {
        $missingHelpers += $helper
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$missingScripts = @()
foreach ($script in $requiredScripts) {
    $scriptPath = Join-Path $repoRoot $script
    if (-not (Test-Path $scriptPath)) {
        $missingScripts += $script
    }
}

if ($missingHelpers.Count -gt 0) {
    Write-Output "[FAIL] Missing PowerShell pwcli helper commands:"
    foreach ($helper in $missingHelpers) {
        Write-Output "  - $helper"
    }
}

if ($missingScripts.Count -gt 0) {
    Write-Output "[FAIL] Missing repo-local pwcli fallback scripts:"
    foreach ($script in $missingScripts) {
        Write-Output "  - $script"
    }
}

if ($missingHelpers.Count -gt 0 -or $missingScripts.Count -gt 0) {
    exit 1
}

Write-Output "[PASS] pwcli helper commands and fallback scripts are available"
