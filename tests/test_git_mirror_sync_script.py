from pathlib import Path


SCRIPT = Path("scripts/sync_main_mirrors.ps1")


def test_git_mirror_sync_script_enforces_cnb_upstream_and_two_remote_mirror_checks():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'Get-GitValue @("branch", "--show-current")' in source
    assert 'Get-GitValue @("status", "--porcelain")' in source
    assert "MERGE_HEAD" in source
    assert "cnb/main" in source
    assert "origin/main" in source
    assert 'Invoke-Git @("merge", "--ff-only", "cnb/main")' in source
    assert "git push $GitHubUrl HEAD:refs/heads/main" in source
    assert "git push $CnbUrl HEAD:refs/heads/main" in source
    assert "Mirror divergence detected" in source


def test_git_mirror_sync_script_configures_origin_dual_push_urls_idempotently():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "git config --unset-all remote.origin.pushurl" in source
    assert 'Invoke-Git @("remote", "set-url", "--push", "origin", $GitHubUrl)' in source
    assert 'Invoke-Git @("remote", "set-url", "--add", "--push", "origin", $CnbUrl)' in source
    assert 'Invoke-Git @("branch", "--set-upstream-to=cnb/main", "main")' in source
    assert "$LASTEXITCODE -notin @(0, 5)" in source
