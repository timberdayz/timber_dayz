from tools.test_component import ComponentTester
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

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


def test_component_tester_does_not_force_profile_level_reuse_for_tiktok_python_export():
    tester = ComponentTester(platform="tiktok", account_id="acc-1")

    assert tester._use_persistent_profile_for_python_component("export") is False


def test_component_tester_does_not_force_profile_level_reuse_for_shopee_python_export():
    tester = ComponentTester(platform="shopee", account_id="acc-1")

    assert tester._use_persistent_profile_for_python_component("export") is False


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
        self.wait_for_load_state = AsyncMock()


@pytest.mark.asyncio
async def test_component_tester_primes_login_gate_page_when_storage_state_starts_at_blank():
    tester = ComponentTester(platform="shopee", account_id="acc-1")
    page = _FakeProbePage()

    await tester._prime_page_for_login_gate(
        page,
        {"login_url": "https://seller.shopee.cn"},
    )

    page.goto.assert_awaited_once_with(
        "https://seller.shopee.cn/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    assert page.wait_for_load_state.await_count >= 2


@pytest.mark.asyncio
async def test_component_tester_primes_login_gate_page_skips_when_already_on_real_url():
    tester = ComponentTester(platform="shopee", account_id="acc-1")
    page = _FakeProbePage("https://seller.shopee.cn/")

    await tester._prime_page_for_login_gate(page, {"login_url": "https://seller.shopee.cn"})

    page.goto.assert_not_awaited()
    assert page.wait_for_load_state.await_count >= 2


def test_component_tester_uses_tiktok_business_probe_url_before_login_url():
    tester = ComponentTester(
        platform="tiktok",
        account_id="acc-1",
        runtime_config={"data_domain": "products"},
    )

    urls = tester._login_gate_probe_urls(
        component_type="export",
        component_name="products_export",
        account_info={"login_url": "https://seller.tiktokglobalshop.com", "shop_region": "SG"},
    )

    assert urls[0] == "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    assert urls[1] == "https://seller.tiktokglobalshop.com/homepage"
    assert urls[2] == "https://seller.tiktokglobalshop.com"


@pytest.mark.asyncio
async def test_component_tester_check_login_gate_waits_for_page_stability_before_detect(monkeypatch):
    tester = ComponentTester(platform="tiktok", account_id="acc-1")
    page = _FakeProbePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    result = SimpleNamespace(phase=None, phase_component_name=None, error=None)

    detected = {}

    class _FakeDetector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform
            self.debug = debug

        async def detect(self, page_arg, wait_for_redirect=True):
            detected["load_state_calls"] = page_arg.wait_for_load_state.await_count
            return SimpleNamespace(
                status=SimpleNamespace(value="logged_in"),
                confidence=0.95,
                matched_pattern="/homepage",
                detected_by="url",
            )

    monkeypatch.setattr("modules.utils.login_status_detector.LoginStatusDetector", _FakeDetector)

    ok = await tester._check_login_gate(page, result, "tiktok/login")

    assert ok is True
    assert detected["load_state_calls"] >= 2


@pytest.mark.asyncio
async def test_component_tester_tiktok_login_gate_allows_login_shell_recovery_before_detect(monkeypatch):
    tester = ComponentTester(platform="tiktok", account_id="acc-1")
    page = _FakeProbePage("https://seller.tiktokshopglobalselling.com/account/login")
    result = SimpleNamespace(phase=None, phase_component_name=None, error=None)
    state = {"count": 0}

    async def _advance(ms: int):
        if ms == 500 and page.url.endswith("/account/login"):
            state["count"] += 1
        if state["count"] >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"

    page.wait_for_timeout = AsyncMock(side_effect=_advance)
    detected = {}

    class _FakeDetector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform
            self.debug = debug

        async def detect(self, page_arg, wait_for_redirect=True):
            detected["url_before_detect"] = page_arg.url
            return SimpleNamespace(
                status=SimpleNamespace(value="logged_in"),
                confidence=0.95,
                matched_pattern="/homepage",
                detected_by="url",
            )

    monkeypatch.setattr("modules.utils.login_status_detector.LoginStatusDetector", _FakeDetector)

    ok = await tester._check_login_gate(page, result, "tiktok/login")

    assert ok is True
    assert detected["url_before_detect"].startswith(
        "https://seller.tiktokshopglobalselling.com/homepage"
    )


@pytest.mark.asyncio
async def test_component_tester_persists_session_after_login_success(monkeypatch):
    tester = ComponentTester(platform="shopee", account_id="shop-1")

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

    ok = await tester._save_context_session(
        fake_context,
        {"account_id": "shop-1", "main_account_id": "main-1"},
    )

    assert ok is True
    assert saved == {
        "platform": "shopee",
        "account_id": "main-1",
        "storage_state": {"cookies": [], "origins": []},
    }


@pytest.mark.asyncio
async def test_component_tester_recreates_context_with_main_account_session_scope(monkeypatch):
    tester = ComponentTester(platform="shopee", account_id="shop-1")

    old_context = AsyncMock()
    new_context = AsyncMock()
    new_page = AsyncMock()
    new_context.new_page = AsyncMock(return_value=new_page)
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=new_context)

    loaded = {}

    async def _fake_load(platform, account_id, account_info, max_age_days=30):
        loaded["platform"] = platform
        loaded["account_id"] = account_id
        loaded["account_info"] = account_info
        loaded["max_age_days"] = max_age_days
        return {"storage_state": {"cookies": ["from-main"], "origins": []}}

    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._load_or_bootstrap_session_async",
        _fake_load,
    )
    monkeypatch.setattr(
        tester,
        "_build_component_browser_context_options",
        AsyncMock(return_value={"storage_state": {"cookies": ["from-main"], "origins": []}}),
    )
    monkeypatch.setattr(tester, "_prime_page_for_login_gate", AsyncMock())

    rebuilt_context, rebuilt_page = await tester._recreate_context_with_saved_session(
        browser=browser,
        old_context=old_context,
        account_info={"account_id": "shop-1", "main_account_id": "main-1"},
    )

    assert rebuilt_context is new_context
    assert rebuilt_page is new_page
    assert loaded["platform"] == "shopee"
    assert loaded["account_id"] == "main-1"


class _FailureBodyLocator:
    async def inner_text(self) -> str:
        return "page body summary"


class _FailureSnapshotPage:
    url = "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"

    async def title(self) -> str:
        return "TikTok Page"

    async def content(self) -> str:
        return "<html><body>snapshot</body></html>"

    def locator(self, selector: str):
        assert selector == "body"
        return _FailureBodyLocator()


@pytest.mark.asyncio
async def test_component_tester_save_failure_artifacts_writes_snapshot_files(tmp_path):
    tester = ComponentTester(
        platform="tiktok",
        account_id="acc-1",
        output_dir=str(tmp_path),
        test_dir=str(tmp_path),
    )
    page = _FailureSnapshotPage()

    snapshot_path = await tester._save_failure_artifacts(page, "products_export", "python_component_1")

    assert snapshot_path is not None
    snapshot_file = Path(snapshot_path)
    assert snapshot_file.exists()

    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert payload["url"] == page.url
    assert payload["title"] == "TikTok Page"

    html_file = Path(payload["html_path"])
    text_file = Path(payload["text_path"])
    assert html_file.exists()
    assert text_file.exists()
    assert html_file.read_text(encoding="utf-8") == "<html><body>snapshot</body></html>"
    assert text_file.read_text(encoding="utf-8") == "page body summary"
