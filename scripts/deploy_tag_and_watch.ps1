# Push tag to trigger production deploy, then watch run and show failed log if any.
# Usage: .\scripts\deploy_tag_and_watch.ps1 v4.24.9
# Prereq: gh CLI installed and logged in (gh auth login).

param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = "Stop"
if (-not $Tag.StartsWith("v")) { $Tag = "v" + $Tag }

Write-Host "[INFO] Pushing tag: $Tag"
git push origin $Tag
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[INFO] Waiting 15s for GitHub to create run..."
Start-Sleep -Seconds 15

$runJson = gh run list --workflow="Deploy to Production" -L 1 --json databaseId,status,conclusion
if (-not $runJson) {
    Write-Host "[WARN] No run found. Check Actions tab manually."
    exit 0
}
$runId = ($runJson | ConvertFrom-Json).databaseId
Write-Host "[INFO] Run ID: $runId - watching..."
gh run watch $runId
$exitCode = $LASTEXITCODE

$runAgain = gh run list --workflow="Deploy to Production" -L 1 --json conclusion -q ".[0].conclusion"
if ($runAgain -eq "failure") {
    Write-Host ""
    Write-Host "[FAIL] Deployment failed. Failed step logs below (copy to Cursor for analysis):"
    Write-Host "-------"
    gh run view $runId --log-failed
}
exit $exitCode
