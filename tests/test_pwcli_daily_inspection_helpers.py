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


def test_daily_inspection_helper_maps_supported_platform_open_commands():
    for command in [
        "Open-PwcliMiaoshou",
        "Open-PwcliShopee",
        "Open-PwcliTiktok",
    ]:
        assert command in HELPER_SOURCE


def test_daily_inspection_helper_no_longer_saves_state():
    """登录态只由浏览器 profile 承载：巡店循环里不得再有「保存会话」。

    以前循环是「打开 -> Read-Host 等待 -> 调 Save-Pwcli*State」；
    现在登录完直接关浏览器即可，循环只负责提示与优雅关闭。
    """
    assert "Save-Pwcli" not in HELPER_SOURCE
    assert "Press Enter to save" not in HELPER_SOURCE
    assert "skip save" not in HELPER_SOURCE
    assert "Read-Host" in HELPER_SOURCE


def test_daily_inspection_helper_tells_operator_to_close_the_browser():
    """循环必须明确提示「关掉浏览器，登录态由 profile 保存」。"""
    loop = HELPER_SOURCE.split("function Start-PwcliDailyInspection", 1)[1]

    assert "close the browser" in loop.lower()
    assert "profile" in loop.lower()
