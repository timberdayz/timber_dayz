from modules.apps.collection_center.browser_config_helper import (
    enforce_official_playwright_browser,
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
