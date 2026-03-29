from pathlib import Path


def test_pwcli_native_usage_is_limited_to_minimal_command_set():
    source = Path("modules/utils/pwcli_native.py").read_text(encoding="utf-8")

    assert "goto <url>" not in source
    assert "dblclick <ref>" not in source
    assert "type <text>" not in source


def test_pwcli_native_does_not_inject_extra_browser_flags_by_default():
    source = Path("modules/utils/pwcli_native.py").read_text(encoding="utf-8")

    assert "--disable-blink-features=AutomationControlled" not in source
    assert "--disable-popup-blocking" not in source
    assert "--disable-background-networking" not in source
    assert "--disable-sync" not in source
    assert "--force-color-profile=srgb" not in source
