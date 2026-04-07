from modules.apps.collection_center.browser_config_helper import (
    enforce_official_playwright_browser,
    get_browser_launch_args,
)


def test_enforce_official_playwright_browser_strips_branded_browser_overrides():
    normalized = enforce_official_playwright_browser(
        {
            "channel": "chrome",
            "executable_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "headless": False,
            "args": ["--start-maximized"],
        }
    )

    assert "channel" not in normalized
    assert "executable_path" not in normalized
    assert normalized["headless"] is False
    assert normalized["args"] == ["--start-maximized"]


def test_get_browser_launch_args_honors_explicit_headless_execution_mode(monkeypatch):
    class _Settings:
        browser_config = {
            "headless": False,
            "slow_mo": 100,
            "args": ["--dev-default"],
        }

    monkeypatch.setattr(
        "backend.utils.config.get_settings",
        lambda: _Settings(),
    )

    launch_args = get_browser_launch_args(execution_mode="headless")

    assert launch_args["headless"] is True
    assert launch_args["slow_mo"] == 0
    assert launch_args["args"] == ["--dev-default"]


def test_get_browser_launch_args_honors_explicit_headed_execution_mode(monkeypatch):
    class _Settings:
        browser_config = {
            "headless": True,
            "slow_mo": 0,
            "args": [],
        }

    monkeypatch.setattr(
        "backend.utils.config.get_settings",
        lambda: _Settings(),
    )

    launch_args = get_browser_launch_args(execution_mode="headed")

    assert launch_args["headless"] is False
