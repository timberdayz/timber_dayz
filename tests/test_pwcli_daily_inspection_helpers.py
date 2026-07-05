from pathlib import Path


HELPER_SOURCE = Path("scripts/pwcli_helpers.ps1").read_text(encoding="utf-8")


def test_pwcli_helpers_exposes_daily_inspection_command():
    assert "function Start-PwcliDailyInspection" in HELPER_SOURCE


def test_daily_inspection_helper_loads_accounts_from_python_json_cli():
    assert "pwcli_daily_inspection.py" in HELPER_SOURCE
    assert '"list-accounts"' in HELPER_SOURCE
    assert '"--format"' in HELPER_SOURCE
    assert '"json"' in HELPER_SOURCE
    assert "ConvertFrom-Json" in HELPER_SOURCE


def test_daily_inspection_helper_maps_supported_platform_open_and_save_commands():
    for command in [
        "Open-PwcliMiaoshou",
        "Open-PwcliShopee",
        "Open-PwcliTiktok",
        "Save-PwcliMiaoshouState",
        "Save-PwcliShopeeState",
        "Save-PwcliTiktokState",
    ]:
        assert command in HELPER_SOURCE


def test_daily_inspection_helper_keeps_save_user_confirmed_and_allows_skip():
    assert "Press Enter to save" in HELPER_SOURCE
    assert "skip save" in HELPER_SOURCE
    assert "Read-Host" in HELPER_SOURCE
