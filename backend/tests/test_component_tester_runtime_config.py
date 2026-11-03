from tools.test_component import (
    ComponentTestResult,
    ComponentTester,
    TestStatus,
)
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import tempfile

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


def test_component_tester_runtime_strategy_prefers_persistent_profile():
    """组件测试器（录制）也以**持久 profile 目录**为登录态载体。

    旧语义是「storage_state 优先」—— 那套会话文件已经是待废除的对象。
    现在录制子进程与正式采集落在**同一个** profile 目录
    （Task 6.5：profile 身份统一为主账号 ID），
    所以「profile 目录存在 → 用 profile」是两侧一致的正确行为。
    """
    tester = ComponentTester(platform="tiktok", account_id="acc-1")

    decision = tester._choose_runtime_strategy(
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        component_type="export",
    )

    assert decision.mode == "persistent_profile"
    assert decision.reason == "persistent_profile_available"


def test_component_tester_and_formal_collection_share_profile_first_default():
    """组件测试与正式采集**共用**同一套策略结论（都以 profile 为载体）。"""
    from modules.apps.collection_center.runtime_session import choose_runtime_strategy

    decision = choose_runtime_strategy(
        platform="shopee",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        execution_kind="component_test",
        component_type="export",
        parallel_mode=False,
    )

    assert decision.mode == "persistent_profile"
    assert decision.reason == "persistent_profile_available"


def test_component_tester_runtime_strategy_delegates_to_shared_runtime_session(monkeypatch):
    tester = ComponentTester(platform="shopee", account_id="acc-1")
    observed = {}

    def _fake_choose_runtime_strategy(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(mode="storage_state_fanout", reason="storage_state_available")

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.choose_runtime_strategy",
        _fake_choose_runtime_strategy,
    )

    decision = tester._choose_runtime_strategy(
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        component_type="export",
    )

    assert decision.mode == "storage_state_fanout"
    assert observed["execution_kind"] == "component_test"
    assert observed["component_type"] == "export"
    assert observed["parallel_mode"] is False


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

    assert "open_storage_state_runtime_bundle" in source
    assert "has_persistent_profile=bool(session_owner_id)" not in source
    assert "runtime_profile_exists(" in source
    assert 'result.error = result.error or getattr(exec_result, "message", None)' not in source


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
        {"login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"},
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

    await tester._prime_page_for_login_gate(
        page,
        {"login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"},
    )

    page.goto.assert_not_awaited()
    assert page.wait_for_load_state.await_count >= 2


def test_component_tester_skips_tiktok_business_probe_urls_before_login():
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

    assert urls == []


def test_component_tester_skips_tiktok_services_probe_urls_before_login():
    tester = ComponentTester(
        platform="tiktok",
        account_id="acc-1",
        runtime_config={"data_domain": "services", "shop_region": "MY"},
    )

    urls = tester._login_gate_probe_urls(
        component_type="export",
        component_name="services_agent_export",
        account_info={"login_url": "https://seller.tiktokshopglobalselling.com/account/login", "shop_region": "MY"},
    )

    assert urls == []


def test_component_tester_skips_tiktok_analytics_probe_urls_before_login():
    tester = ComponentTester(
        platform="tiktok",
        account_id="acc-1",
        runtime_config={"data_domain": "analytics", "shop_region": "MY"},
    )

    urls = tester._login_gate_probe_urls(
        component_type="export",
        component_name="analytics_export",
        account_info={"login_url": "https://seller.tiktokshopglobalselling.com/account/login", "shop_region": "MY"},
    )

    assert urls == []


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
async def test_component_tester_no_longer_persists_session_after_login_success():
    """登录成功后**不再写会话文件**：登录态只由 Chromium 持久 profile 承载（D5 / R1）。

    旧的 ``_save_context_session`` 入口连同 ``SessionManager.save_session``
    一起下线 —— 「人工保存会话」这个概念整体废除。
    """
    tester = ComponentTester(platform="shopee", account_id="shop-1")

    assert not hasattr(tester, "_save_context_session"), (
        "组件测试子进程仍保留会话文件写入入口"
    )
    from modules.utils.sessions.session_manager import SessionManager

    assert not hasattr(SessionManager, "save_session"), "会话文件写入口仍存在"


@pytest.mark.asyncio
async def test_component_tester_rebuild_uses_main_account_profile_scope_without_session_file(monkeypatch):
    """重开走**主账号的 profile 目录**(profile 单一载体), 不再读会话文件。

    旧实现是「读会话文件 -> 重建 context」, 与采集侧已脱节; 现在改成
    「在同一个 profile 目录上重开持久 context」。
    """
    tester = ComponentTester(platform="shopee", account_id="shop-1")

    profile_dir = Path(tempfile.gettempdir()) / "t65-profile-scope" / "main-1"
    opened: list = []
    snapshotted: list = []

    async def _fake_open_persistent_runtime_bundle(**kwargs):
        opened.append(kwargs)
        return SimpleNamespace(context=AsyncMock(), page=AsyncMock())

    def _fake_snapshot(platform, account_id):
        snapshotted.append((platform, account_id))
        return {"storage_state": {"cookies": ["from-main"], "origins": []}}

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        _fake_open_persistent_runtime_bundle,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.prime_runtime_page_for_login_gate",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.snapshot_profile_storage_state_sync",
        _fake_snapshot,
    )
    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_dir,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.python_component_adapter.create_adapter",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        tester,
        "_run_login_with_verification_support",
        AsyncMock(return_value=SimpleNamespace(success=True)),
    )
    # 账号锁用假实现(避免按住进程内锁单例, 污染同会话其它用例)
    monkeypatch.setattr(
        tester,
        "_open_profile_session_lock",
        AsyncMock(return_value=None),
    )

    ok, _new_context, _new_page = await tester._run_headful_login_fallback(
        browser_type=object(),
        old_context=AsyncMock(),
        account_info={"account_id": "shop-1", "main_account_id": "main-1"},
        login_class=object(),
        component_name="shopee/login",
        result=ComponentTestResult(
            component_name="login",
            platform="shopee",
            status=TestStatus.PENDING,
        ),
    )

    assert ok is True
    assert opened, "回退必须在持久 profile 上重开 context"
    for call in opened:
        assert call["session_owner_id"] == "main-1"
        assert call["profile_path_override"] == str(profile_dir)
    # 会话文件不再参与这条链路；回退直接在持久 profile 上重开
    assert snapshotted == []


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
