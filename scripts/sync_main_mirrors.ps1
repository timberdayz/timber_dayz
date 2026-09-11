param(
    [switch]$Configure,
    [switch]$Sync,
    [string]$GitHubUrl = "https://github.com/timberdayz/timber_dayz.git",
    [string]$CnbUrl = "https://cnb.cool/timberdayz/xihong_erp"
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([string[]]$Arguments)

    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $output = & git @Arguments 2>$stderrPath
        $exitCode = $LASTEXITCODE
        $stderr = [System.IO.File]::ReadAllText($stderrPath)
        if ($exitCode -ne 0) {
            throw "git $($Arguments -join ' ') failed: $stderr"
        }
        return ($output -join [Environment]::NewLine).Trim()
    } finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-GitValue {
    param([string[]]$Arguments)

    return (Invoke-Git $Arguments).Trim()
}

function Test-GitAncestor {
    param([string]$Ancestor, [string]$Descendant)

    & git merge-base --is-ancestor $Ancestor $Descendant
    return $LASTEXITCODE -eq 0
}

function Assert-MainSafety {
    $branch = Get-GitValue @("branch", "--show-current")
    if ($branch -ne "main") {
        throw "This command only runs on main; current branch is '$branch'."
    }
    if ((Get-GitValue @("status", "--porcelain"))) {
        throw "Working tree is not clean. Commit or stash changes before mirror sync."
    }

    $mergeHead = Get-GitValue @("rev-parse", "--git-path", "MERGE_HEAD")
    $rebaseMerge = Get-GitValue @("rev-parse", "--git-path", "rebase-merge")
    $rebaseApply = Get-GitValue @("rev-parse", "--git-path", "rebase-apply")
    if ((Test-Path $mergeHead) -or (Test-Path $rebaseMerge) -or (Test-Path $rebaseApply)) {
        throw "A merge or rebase is in progress. Finish or abort it before mirror sync."
    }
}

function Configure-MirrorRemotes {
    $null = Invoke-Git @("remote", "set-url", "origin", $GitHubUrl)
    $hasCnb = & git remote get-url cnb 2>$null
    if ($LASTEXITCODE -eq 0) {
        $null = Invoke-Git @("remote", "set-url", "cnb", $CnbUrl)
    } else {
        $null = Invoke-Git @("remote", "add", "cnb", $CnbUrl)
    }

    & git config --unset-all remote.origin.pushurl 2>$null
    if ($LASTEXITCODE -notin @(0, 5)) {
        throw "Unable to clear existing origin push URLs."
    }
    # Recreate the push list atomically from the intended two-mirror contract.
    $null = Invoke-Git @("remote", "set-url", "--push", "origin", $GitHubUrl)
    $null = Invoke-Git @("remote", "set-url", "--add", "--push", "origin", $CnbUrl)
    $null = Invoke-Git @("fetch", "--prune", "cnb")
    $null = Invoke-Git @("branch", "--set-upstream-to=origin/main", "main")
    $null = Invoke-Git @("config", "branch.main.vscode-merge-base", "origin/main")

    Write-Host "XIHONG_GIT_MIRROR_CONFIGURED=cnb/main"
}

function Assert-MirrorsAligned {
    $originSha = Get-GitValue @("rev-parse", "origin/main")
    $cnbSha = Get-GitValue @("rev-parse", "cnb/main")
    if ($originSha -ne $cnbSha) {
        throw "Mirror divergence detected: GitHub origin/main=$originSha; CNB cnb/main=$cnbSha. Reconcile history before syncing."
    }
    return $originSha
}

Assert-MainSafety
if ($Configure) {
    Configure-MirrorRemotes
}

$null = Invoke-Git @("fetch", "--prune", "origin")
$null = Invoke-Git @("fetch", "--prune", "cnb")
$remoteSha = Assert-MirrorsAligned
$headSha = Get-GitValue @("rev-parse", "HEAD")

if ($headSha -ne $remoteSha) {
    if (Test-GitAncestor $headSha "cnb/main") {
        $null = Invoke-Git @("merge", "--ff-only", "cnb/main")
        $headSha = Get-GitValue @("rev-parse", "HEAD")
    } elseif (-not (Test-GitAncestor "cnb/main" $headSha)) {
        throw "Local main diverges from cnb/main. Reconcile history in a repair worktree before syncing."
    }
}

if (-not $Sync) {
    Write-Host "XIHONG_GIT_MIRROR_READY=$headSha"
    Write-Host "Run .\\scripts\\sync_main_mirrors.ps1 -Sync to mirror this main commit."
    exit 0
}

& git push $GitHubUrl HEAD:refs/heads/main
if ($LASTEXITCODE -ne 0) {
    throw "GitHub push failed; CNB was not changed."
}
& git push $CnbUrl HEAD:refs/heads/main
if ($LASTEXITCODE -ne 0) {
    throw "CNB push failed after GitHub accepted the commit. Re-run diagnostics before any retry."
}

$null = Invoke-Git @("fetch", "--prune", "origin")
$null = Invoke-Git @("fetch", "--prune", "cnb")
$verifiedRemoteSha = Assert-MirrorsAligned
$verifiedHeadSha = Get-GitValue @("rev-parse", "HEAD")
if ($verifiedHeadSha -ne $verifiedRemoteSha) {
    throw "Mirror verification failed: local main=$verifiedHeadSha; remote main=$verifiedRemoteSha."
}

Write-Host "XIHONG_GIT_MIRROR_SYNCED=$verifiedHeadSha"
