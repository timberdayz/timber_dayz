from pathlib import Path


def test_pwcli_wrapper_uses_repo_native_cli():
    source = Path("scripts/pwcli.ps1").read_text(encoding="utf-8")

    assert "@playwright/cli" not in source
    assert "pwcli_native.py" in source
