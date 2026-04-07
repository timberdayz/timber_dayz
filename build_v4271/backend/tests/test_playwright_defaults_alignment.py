from pathlib import Path


ACTIVE_PLAYWRIGHT_PATHS = [
    Path("modules/apps/collection_center/browser_config_helper.py"),
    Path("modules/apps/collection_center/executor_v2.py"),
    Path("modules/collectors/base/playwright_collector.py"),
]


def test_active_playwright_paths_do_not_pin_legacy_chrome_user_agent():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_PLAYWRIGHT_PATHS)

    assert "Chrome/120.0.0.0" not in combined
    assert "disable-blink-features=AutomationControlled" not in combined


def test_pwcli_sop_uses_supported_minimal_native_commands():
    source = Path("docs/guides/PWCLI_AGENT_COLLECTION_SOP.md").read_text(encoding="utf-8")

    unsupported = [
        "pwcli hover",
        "pwcli tab-list",
        "pwcli tab-select",
        "pwcli tracing-start",
        "pwcli tracing-stop",
        "pwcli console warning",
        "pwcli network",
    ]

    for marker in unsupported:
        assert marker not in source
