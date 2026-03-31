from tools.test_component import ComponentTester
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def test_component_tester_builds_export_runtime_config():
    tester = ComponentTester(
        platform="shopee",
        account_id="acc-1",
        output_dir="temp/test_results",
        runtime_config={
            "data_domain": "services",
            "sub_domain": "agent",
            "services_subtype": "agent",
            "granularity": "weekly",
            "time_selection": {
                "mode": "preset",
                "preset": "last_7_days",
            },
        },
    )

    cfg = tester._build_runtime_component_config()

    assert cfg["data_domain"] == "services"
    assert cfg["sub_domain"] == "agent"
    assert cfg["services_subtype"] == "agent"
    assert cfg["granularity"] == "weekly"
    assert cfg["time_selection"] == {
        "mode": "preset",
        "preset": "last_7_days",
    }
    assert cfg["params"]["granularity"] == "weekly"
    assert cfg["params"]["sub_domain"] == "agent"


def test_component_tester_does_not_reference_removed_public_account_info_attr():
    source = Path("tools/test_component.py").read_text(encoding="utf-8")

    assert "self.account_info" not in source


def test_component_tester_uses_official_playwright_default_browser():
    source = Path("tools/test_component.py").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSER_CHANNEL" not in source
    assert "channel=browser_channel" not in source


def test_component_tester_disables_reused_persistent_context_for_login():
    tester = ComponentTester(platform="tiktok", account_id="acc-1")

    assert tester._persistent_context_mode("login") is None


def test_component_tester_uses_reused_persistent_context_for_export():
    tester = ComponentTester(platform="tiktok", account_id="acc-1")

    assert tester._persistent_context_mode("export") == "reused"


def test_component_tester_uses_reused_persistent_context_for_navigation():
    tester = ComponentTester(platform="miaoshou", account_id="acc-1")

    assert tester._persistent_context_mode("navigation") == "reused"


def test_component_tester_skip_login_disables_reused_persistent_context_for_non_login_components():
    tester = ComponentTester(platform="shopee", account_id="acc-1", skip_login=True)

    assert tester._persistent_context_mode("export") is None


def test_component_tester_login_readiness_candidates_include_tiktok_specific_signals():
    tester = ComponentTester(platform="tiktok", account_id="acc-1")

    selectors = [item[0] for item in tester._login_readiness_candidates("login")]

    assert "input[placeholder*='手机号']" in selectors
    assert "input[placeholder*='邮箱']" in selectors
    assert "text=使用邮箱登录" in selectors
    assert "input[placeholder*='验证码']" in selectors


def test_component_tester_login_readiness_candidates_include_shopee_specific_signals():
    tester = ComponentTester(platform="shopee", account_id="acc-1")

    selectors = [item[0] for item in tester._login_readiness_candidates("login")]

    assert "input[name='loginKey']" in selectors
    assert "button:has-text('登录')" in selectors


def test_component_tester_headed_paths_request_start_maximized():
    source = Path("tools/test_component.py").read_text(encoding="utf-8")

    assert "args=['--start-maximized'] if not self.headless else []" in source


def test_component_tester_headed_persistent_context_does_not_force_fixed_viewport():
    source = Path("tools/test_component.py").read_text(encoding="utf-8")

    assert "'viewport': None if not self.headless else" in source


class _FakeProbePage:
    def __init__(self, url: str = "about:blank"):
        self.url = url
        self.goto = AsyncMock()
        self.wait_for_timeout = AsyncMock()


@pytest.mark.asyncio
async def test_component_tester_primes_login_gate_page_when_storage_state_starts_at_blank():
    tester = ComponentTester(platform="shopee", account_id="acc-1")
    page = _FakeProbePage()

    await tester._prime_page_for_login_gate(page, {"login_url": "https://seller.shopee.cn"})

    page.goto.assert_awaited_once_with(
        "https://seller.shopee.cn",
        wait_until="domcontentloaded",
        timeout=60000,
    )


@pytest.mark.asyncio
async def test_component_tester_primes_login_gate_page_skips_when_already_on_real_url():
    tester = ComponentTester(platform="shopee", account_id="acc-1")
    page = _FakeProbePage("https://seller.shopee.cn/")

    await tester._prime_page_for_login_gate(page, {"login_url": "https://seller.shopee.cn"})

    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_component_tester_persists_session_after_login_success(monkeypatch):
    tester = ComponentTester(platform="shopee", account_id="acc-1")

    fake_context = AsyncMock()
    fake_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

    saved = {}

    async def _fake_save(platform, account_id, storage_state):
        saved["platform"] = platform
        saved["account_id"] = account_id
        saved["storage_state"] = storage_state
        return True

    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._save_session_async",
        _fake_save,
    )

    ok = await tester._save_context_session(fake_context, {"account_id": "acc-1"})

    assert ok is True
    assert saved == {
        "platform": "shopee",
        "account_id": "acc-1",
        "storage_state": {"cookies": [], "origins": []},
    }
