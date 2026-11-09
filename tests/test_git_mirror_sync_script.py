from pathlib import Path


SCRIPT = Path("scripts/sync_main_mirrors.ps1")


def test_git_mirror_sync_script_enforces_cnb_upstream_and_two_remote_mirror_checks():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "$stderrPath = [System.IO.Path]::GetTempFileName()" in source
    assert "2>$stderrPath" in source
    assert "$PSNativeCommandUseErrorActionPreference = $false" in source
    assert "$previousErrorActionPreference = $ErrorActionPreference" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert 'Get-GitValue @("branch", "--show-current")' in source
    assert 'Get-GitValue @("status", "--porcelain")' in source
    assert "MERGE_HEAD" in source
    assert "cnb/main" in source
    assert "origin/main" in source
    assert 'Invoke-Git @("merge", "--ff-only", "cnb/main")' in source
    # ⚠️ 推送改走 ``Invoke-GitPush`` 包装：git 的 push 进度写在 stderr，
    # Windows PowerShell 5 下被捕获的原生 stderr 会变成终止性错误，
    # 曾导致「GitHub 推成功、CNB 没推」的双端分叉 ⇒ 封装里显式收 stderr 再回传退出码。
    assert 'Invoke-GitPush @("push", $GitHubUrl, "HEAD:refs/heads/main")' in source
    assert 'Invoke-GitPush @("push", $CnbUrl, "HEAD:refs/heads/main")' in source
    assert "Mirror divergence detected" in source


def test_git_mirror_sync_script_configures_origin_dual_push_urls_idempotently():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "https://github.com/timberdayz/timber_dayz.git" in source
    assert "git config --unset-all remote.origin.pushurl" in source
    assert 'Invoke-Git @("remote", "set-url", "--push", "origin", $GitHubUrl)' in source
    assert (
        'Invoke-Git @("remote", "set-url", "--add", "--push", "origin", $CnbUrl)'
        in source
    )
    assert 'Invoke-Git @("branch", "--set-upstream-to=origin/main", "main")' in source
    assert (
        'Invoke-Git @("config", "branch.main.vscode-merge-base", "origin/main")'
        in source
    )
    assert "$LASTEXITCODE -notin @(0, 5)" in source
