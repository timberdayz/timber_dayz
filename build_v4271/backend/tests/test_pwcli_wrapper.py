from pathlib import Path


def test_pwcli_wrapper_uses_repo_native_cli():
    source = Path("scripts/pwcli.ps1").read_text(encoding="utf-8")

    assert "@playwright/cli" not in source
    assert "pwcli_native.py" in source


def test_pwcap_wrapper_uses_bound_session_and_non_terminating_native_stderr_handling():
    source = Path("scripts/pw-cap.ps1").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_CLI_SESSION" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert "-s=$ResolvedSession" in source
