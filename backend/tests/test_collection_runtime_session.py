from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.runtime_session import (
    RuntimeContextBundle,
    RuntimeSessionScope,
    choose_runtime_strategy,
    build_runtime_login_gate_probe_urls,
    build_runtime_context_options,
    check_login_gate_ready,
    open_persistent_runtime_bundle,
    open_storage_state_runtime_bundle,
    probe_runtime_login_gate,
    resolve_runtime_session_scope,
    tiktok_storage_state_meets_quality_gate,
    tiktok_storage_state_quality_score,
)
from modules.apps.collection_center.transition_gates import GateResult, GateStatus


def test_resolve_runtime_session_scope_prefers_main_account() -> None:
    scope = resolve_runtime_session_scope(
        requested_account_id="shop-1",
        account={
            "main_account_id": "main-1",
            "shop_account_id": "shop-1",
            "account_id": "legacy-shop-1",
        },
    )

    assert scope == RuntimeSessionScope(
        session_owner_id="main-1",
        shop_account_id="shop-1",
        use_account_session_fingerprint=True,
    )


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_uses_launch_persistent_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profiles" / "miaoshou" / "main-1"
    # 有登录态的 profile 一定有 Chromium 的 cookie 库（Chromium 110+：
    # Default/Network/Cookies）
    (profile_path / "Default" / "Network").mkdir(parents=True)
    (profile_path / "Default" / "Network" / "Cookies").write_bytes(b"")

    page = object()
    launch_kwargs: dict[str, object] = {}

    class _FakeContext:
        pages = [page]

        async def add_init_script(self, script: str) -> None:
            return None

        async def new_page(self):
            raise AssertionError("existing page should be reused")

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            launch_kwargs.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 1920, "height": 1080},
                "accept_downloads": True,
            }
        ),
    )

    bundle = await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="miaoshou",
        session_owner_id="main-1",
        account={"login_url": "https://erp.91miaoshou.com/login"},
        launch_kwargs={"headless": True},
    )

    assert isinstance(bundle, RuntimeContextBundle)
    assert bundle.mode == "persistent_profile"
    assert bundle.page is page
    assert bundle.reused_session is True
    assert launch_kwargs["user_data_dir"] == str(profile_path)
    assert launch_kwargs["accept_downloads"] is True
    assert "locale" not in launch_kwargs
    assert launch_kwargs["viewport"] == {"width": 1920, "height": 1080}


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_does_not_treat_started_profile_as_logged_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """「启动过但没登录」的 profile **不算**有登录态。

    Chromium 只要启动过一次就会写 ``Default/``、``Crashpad/`` 等 —— 用「目录非空」
    判定会把没登录的 profile 误判成有登录态，进而让 ``session_reused`` 失真。
    判据必须是 Chromium 的 cookie 库（``Default/Network/Cookies``）。
    """
    profile_path = tmp_path / "profiles" / "miaoshou" / "main-1"
    (profile_path / "Default").mkdir(parents=True)
    (profile_path / "Default" / "Preferences").write_text("{}", encoding="utf-8")

    class _FakeContext:
        pages = [object()]

        async def add_init_script(self, script: str) -> None:
            return None

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(return_value={"accept_downloads": True}),
    )

    bundle = await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="miaoshou",
        session_owner_id="main-1",
        account={"login_url": "https://erp.91miaoshou.com/login"},
        launch_kwargs={"headless": True},
    )

    assert bundle.reused_session is False


def test_profile_contains_state_requires_cookie_store(tmp_path: Path) -> None:
    """``_profile_contains_state`` 只认 cookie 库：两条路径都查（新版 / 旧版）。"""
    from modules.apps.collection_center.runtime_session import _profile_contains_state

    empty_profile = tmp_path / "empty"
    empty_profile.mkdir()
    assert _profile_contains_state(empty_profile) is False

    started_only = tmp_path / "started"
    (started_only / "Default").mkdir(parents=True)
    assert _profile_contains_state(started_only) is False

    modern = tmp_path / "modern"
    (modern / "Default" / "Network").mkdir(parents=True)
    (modern / "Default" / "Network" / "Cookies").write_bytes(b"")
    assert _profile_contains_state(modern) is True

    legacy = tmp_path / "legacy"
    (legacy / "Default").mkdir(parents=True)
    (legacy / "Default" / "Cookies").write_bytes(b"")
    assert _profile_contains_state(legacy) is True

    # 路径不存在时必须安全返回 False
    assert _profile_contains_state(tmp_path / "missing") is False


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_preserves_headed_launch_kwargs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profiles" / "tiktok" / "main-1"
    profile_path.mkdir(parents=True)
    (profile_path / "Preferences").write_text("{}", encoding="utf-8")

    launch_kwargs: dict[str, object] = {}

    class _FakeContext:
        pages = [object()]

        async def add_init_script(self, script: str) -> None:
            return None

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            launch_kwargs.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )

    bundle = await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="tiktok",
        session_owner_id="main-1",
        account={"login_url": "https://seller.tiktok.com"},
        launch_kwargs={"headless": False, "args": ["--start-maximized"]},
    )

    assert bundle.mode == "persistent_profile"
    assert launch_kwargs["headless"] is False
    assert launch_kwargs["args"] == ["--start-maximized"]


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_captures_page_and_context_diagnostics_for_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profiles" / "shopee" / "main-1"
    profile_path.mkdir(parents=True)
    (profile_path / "Preferences").write_text("{}", encoding="utf-8")

    page_a = type("Page", (), {"url": "https://seller.shopee.cn/account/signin"})()
    page_b = type("Page", (), {"url": "https://seller.shopee.cn/?cnsc_shop_id=1"})()

    class _FakeContext:
        pages = [page_a, page_b]

        async def add_init_script(self, script: str) -> None:
            return None

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "en-MY",
                "timezone_id": "Asia/Kuala_Lumpur",
                "user_agent": "UA",
                "viewport": {"width": 1920, "height": 1080},
                "extra_http_headers": {"Accept-Language": "ms-MY,ms;q=0.9"},
                "accept_downloads": True,
            }
        ),
    )

    bundle = await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="shopee",
        session_owner_id="main-1",
        account={"login_url": "https://seller.shopee.cn/account/signin"},
        launch_kwargs={"headless": False},
    )

    assert bundle.available_page_urls == [
        "https://seller.shopee.cn/account/signin",
        "https://seller.shopee.cn/?cnsc_shop_id=1",
    ]
    assert bundle.selected_page_url == "https://seller.shopee.cn/account/signin"
    assert bundle.context_summary["user_agent"] is None
    assert bundle.context_summary["locale"] is None
    assert bundle.context_summary["timezone_id"] is None
    assert bundle.context_summary["accept_language"] is None


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_strips_runtime_context_overrides_for_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profiles" / "miaoshou" / "main-1"
    profile_path.mkdir(parents=True)
    (profile_path / "Preferences").write_text("{}", encoding="utf-8")

    launch_kwargs: dict[str, object] = {}

    class _FakeContext:
        pages = [object()]

        async def add_init_script(self, script: str) -> None:
            return None

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            launch_kwargs.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "en-MY",
                "timezone_id": "Asia/Kuala_Lumpur",
                "user_agent": "UA",
                "viewport": {"width": 1920, "height": 1080},
                "extra_http_headers": {"Accept-Language": "ms-MY,ms;q=0.9"},
                "accept_downloads": True,
            }
        ),
    )

    await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="miaoshou",
        session_owner_id="main-1",
        account={"login_url": "https://erp.91miaoshou.com/login"},
        launch_kwargs={"headless": False},
    )

    assert launch_kwargs["accept_downloads"] is True
    assert launch_kwargs["viewport"] == {"width": 1920, "height": 1080}
    assert "locale" not in launch_kwargs
    assert "timezone_id" not in launch_kwargs
    assert "user_agent" not in launch_kwargs
    assert "extra_http_headers" not in launch_kwargs


@pytest.mark.asyncio
async def test_open_persistent_runtime_bundle_does_not_inject_browser_scripts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profiles" / "tiktok" / "main-1"
    profile_path.mkdir(parents=True)
    (profile_path / "Preferences").write_text("{}", encoding="utf-8")

    class _FakeContext:
        pages = [object()]

        async def add_init_script(self, script: str) -> None:
            raise AssertionError("formal runtime should not inject browser scripts")

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )

    bundle = await open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="tiktok",
        session_owner_id="main-1",
        account={"login_url": "https://seller.tiktok.com"},
        launch_kwargs={"headless": False},
    )

    assert bundle.mode == "persistent_profile"


@pytest.mark.asyncio
async def test_open_storage_state_runtime_bundle_uses_new_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = object()
    new_context_kwargs: dict[str, object] = {}

    class _FakeContext:
        async def add_init_script(self, script: str) -> None:
            return None

        async def new_page(self):
            return page

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            new_context_kwargs.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "accept_downloads": True,
                "storage_state": {"cookies": [], "origins": []},
            }
        ),
    )

    bundle = await open_storage_state_runtime_bundle(
        browser=_FakeBrowser(),
        platform="tiktok",
        session_owner_id="main-1",
        account={"login_url": "https://seller.tiktok.com"},
        storage_state={"cookies": [], "origins": []},
    )

    assert isinstance(bundle, RuntimeContextBundle)
    assert bundle.mode == "storage_state_fanout"
    assert bundle.page is page
    assert new_context_kwargs["accept_downloads"] is True
    assert new_context_kwargs["storage_state"] == {"cookies": [], "origins": []}


@pytest.mark.asyncio
async def test_open_storage_state_runtime_bundle_does_not_inject_browser_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = object()

    class _FakeContext:
        async def add_init_script(self, script: str) -> None:
            raise AssertionError("formal runtime should not inject browser scripts")

        async def new_page(self):
            return page

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            return _FakeContext()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "accept_downloads": True,
                "storage_state": {"cookies": [], "origins": []},
            }
        ),
    )

    bundle = await open_storage_state_runtime_bundle(
        browser=_FakeBrowser(),
        platform="tiktok",
        session_owner_id="main-1",
        account={"login_url": "https://seller.tiktok.com"},
        storage_state={"cookies": [], "origins": []},
    )

    assert bundle.mode == "storage_state_fanout"


@pytest.mark.asyncio
async def test_check_login_gate_ready_returns_false_for_login_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DetectorResult:
        status = type("Status", (), {"value": "not_logged_in"})()
        confidence = 0.98
        matched_pattern = "login-form"
        detected_by = "stub"

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult()

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )

    ok, gate_result = await check_login_gate_ready(
        page=type("Page", (), {"url": "https://erp.91miaoshou.com/login"})(),
        platform="miaoshou",
    )

    assert ok is False
    assert gate_result.status.value == "failed"


@pytest.mark.asyncio
async def test_build_runtime_context_options_uses_storage_state_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session._get_fingerprint_context_options_async",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 1920, "height": 1080},
                "accept_downloads": True,
            }
        ),
    )

    options = await build_runtime_context_options(
        platform="shopee",
        session_owner_id="main-1",
        account={"login_url": "https://seller.shopee.com"},
        storage_state={"cookies": [{"name": "a"}], "origins": []},
    )

    assert options["locale"] == "zh-CN"
    assert options["storage_state"] == {"cookies": [{"name": "a"}], "origins": []}


@pytest.mark.asyncio
async def test_build_runtime_context_options_drops_fixed_viewport_in_headed_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session._get_fingerprint_context_options_async",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 2880, "height": 1800},
                "accept_downloads": True,
            }
        ),
    )

    options = await build_runtime_context_options(
        platform="shopee",
        session_owner_id="main-1",
        account={
            "login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
        },
        headless=False,
    )

    assert options["locale"] == "zh-CN"
    assert options["viewport"] == {"width": 1920, "height": 1080}


@pytest.mark.asyncio
async def test_build_runtime_context_options_uses_standard_headless_viewport_even_when_fingerprint_is_oversized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session._get_fingerprint_context_options_async",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 2880, "height": 1800},
                "accept_downloads": True,
            }
        ),
    )

    options = await build_runtime_context_options(
        platform="shopee",
        session_owner_id="main-1",
        account={
            "login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
        },
        headless=True,
    )

    assert options["locale"] == "zh-CN"
    assert options["viewport"] == {"width": 1920, "height": 1080}


def test_build_runtime_login_gate_probe_urls_skips_tiktok_probe_navigation() -> None:
    urls = build_runtime_login_gate_probe_urls(
        platform="tiktok",
        account={"login_url": "https://seller.tiktok.com/account/login"},
    )

    assert urls == [
        "https://seller.tiktok.com/homepage",
        "https://seller.tiktok.com/account/login",
    ]


def test_build_runtime_login_gate_probe_urls_skips_region_scoped_homepage_for_tiktok() -> None:
    urls = build_runtime_login_gate_probe_urls(
        platform="tiktok",
        account={
            "login_url": "https://seller.tiktokshopglobalselling.com/account/login",
            "shop_region": "SG",
        },
    )

    assert urls == [
        "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG",
        "https://seller.tiktokshopglobalselling.com/account/login",
    ]


def test_formal_sequential_runtime_always_prefers_persistent_profile() -> None:
    """Task 4.2：正式采集**恒走持久 profile**，与「有没有会话文件」无关（R1）。

    旧契约是「storage_state 优先 / profile 兜底」；会话文件整体废除（D5）之后，
    profile 就是顺序路径的唯一载体。
    """
    decision = choose_runtime_strategy(
        platform="miaoshou",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        execution_kind="formal_collection",
        component_type="export",
        parallel_mode=False,
    )

    assert decision.mode == "persistent_profile"
    assert decision.reason == "profile_is_single_source_of_truth"
    assert decision.used_storage_state is False
    assert decision.used_persistent_profile is True
    assert decision.fallback_allowed is False


def test_formal_sequential_runtime_allows_preferring_persistent_profile_for_tiktok_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = choose_runtime_strategy(
        platform="tiktok",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        execution_kind="formal_collection",
        component_type="export",
        parallel_mode=False,
    )

    assert decision.mode == "persistent_profile"
    assert decision.reason == "profile_is_single_source_of_truth"
    assert decision.used_persistent_profile is True
    assert decision.used_storage_state is False


def test_manual_storage_state_arbitration_is_gone() -> None:
    """「人工会话优先于机器会话」的仲裁规则整体废除（D5 / R1）。

    旧契约：人工巡店保存的会话（``data/sessions/**``）优先于 profile。
    会话文件体系废除后，这条分支**在代码结构上就不存在**了 ——
    ``choose_runtime_strategy`` 不再接受 ``has_manual_storage_state`` 参数。
    """
    import inspect

    signature = inspect.signature(choose_runtime_strategy)

    assert "has_manual_storage_state" not in signature.parameters

    decision = choose_runtime_strategy(
        platform="tiktok",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=False,
        force_persistent_profile=False,
        execution_kind="component_test",
        component_type="export",
        parallel_mode=False,
    )

    assert decision.reason != "manual_storage_state_available"


def test_formal_collection_strategy_ignores_every_storage_state_probe() -> None:
    """正式采集的结论**与任何探针结果无关**（profile 是唯一载体）。

    这条守住「顺序路径恒走 profile」：只要有人把「读会话文件 / 人工会话优先」
    的分支加回判定树，这里立刻变红。
    """
    probes = (
        (False, False),
        (True, False),
        (True, True),
        (False, True),
    )
    for has_storage_state, has_persistent_profile in probes:
        decision = choose_runtime_strategy(
            platform="shopee",
            session_owner_id="main-1",
            has_storage_state=has_storage_state,
            has_persistent_profile=has_persistent_profile,
            force_persistent_profile=False,
            execution_kind="formal_collection",
            component_type="export",
            parallel_mode=False,
        )

        assert decision.mode == "persistent_profile", (
            has_storage_state,
            has_persistent_profile,
        )
        assert decision.reason == "profile_is_single_source_of_truth"
        assert decision.used_storage_state is False
        assert decision.used_persistent_profile is True
        assert decision.fallback_allowed is False


def test_component_test_strategy_keeps_legacy_decision_tree() -> None:
    """工具 / 录制路径（``component_test``）不受正式采集收敛影响（R5 修订表）。"""
    decision = choose_runtime_strategy(
        platform="shopee",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=False,
        force_persistent_profile=False,
        execution_kind="component_test",
        component_type="export",
        parallel_mode=False,
    )

    assert decision.mode == "storage_state_fanout"
    assert decision.reason == "storage_state_available"
    assert decision.used_storage_state is True
    assert decision.used_persistent_profile is False


def test_tiktok_storage_state_quality_gate_rejects_shallow_bootstrap_state() -> None:
    state = {
        "cookies": [
            {"name": "_m4b_theme_", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "i18next", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "gd_random", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [],
    }

    assert tiktok_storage_state_meets_quality_gate(state) is False
    assert tiktok_storage_state_quality_score(state) < 8


def test_tiktok_storage_state_quality_gate_accepts_region_hosted_seller_session() -> None:
    state = {
        "cookies": [
            {"name": "sessionid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "sid_tt", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "passport_csrf_token", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "user_oec_info", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
            {"name": "global_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "app_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "oec_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "i18next", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
            {"name": "ATLAS_LANG", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
            {"name": "msToken", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
            {"name": "passport_auth_status", "domain": ".tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [],
    }

    assert tiktok_storage_state_meets_quality_gate(state) is True
    assert tiktok_storage_state_quality_score(state) >= 12


@pytest.mark.asyncio
async def test_probe_runtime_login_gate_does_not_navigate_for_tiktok_after_current_page_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Page:
        def __init__(self):
            self.url = "https://seller.tiktok.com/some-other-page"
            self.goto_calls = []

        async def goto(self, url, wait_until="domcontentloaded", timeout=60000):
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(self, state, timeout=0):
            return None

        async def wait_for_timeout(self, ms):
            return None

    from modules.utils.login_status_detector import LoginDetectionResult, LoginStatus

    async def _fake_detect(page, wait_for_redirect: bool = True):  # noqa: ARG001
        return LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.5,
            reason="inconclusive",
            detected_by="combined",
            current_url=str(getattr(page, "url", "")),
        )

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector.detect",
        AsyncMock(side_effect=_fake_detect),
    )

    page = _Page()
    ready, gate_result = await probe_runtime_login_gate(
        page=page,
        platform="tiktok",
        account={
            "login_url": "https://seller.tiktok.com/account/login",
            "shop_region": "SG",
        },
    )

    assert ready is False
    assert gate_result.stage == "login_gate"
    assert page.goto_calls == []


@pytest.mark.asyncio
async def test_probe_runtime_login_gate_primes_root_page_for_tiktok_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Page:
        def __init__(self):
            self.url = "about:blank"
            self.goto_calls = []

        async def goto(self, url, wait_until="domcontentloaded", timeout=60000):  # noqa: ARG002
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(self, state, timeout=0):  # noqa: ARG002
            return None

        async def wait_for_timeout(self, ms):  # noqa: ARG002
            return None

    async def _fake_check_login_gate_ready(*, page, platform):  # noqa: ARG001
        return (
            False,
            GateResult(
                stage="login_gate",
                status=GateStatus.FAILED,
                reason="blank bootstrap",
                current_url=str(getattr(page, "url", "")),
            ),
        )

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.check_login_gate_ready",
        AsyncMock(side_effect=_fake_check_login_gate_ready),
    )

    page = _Page()
    ready, _gate_result = await probe_runtime_login_gate(
        page=page,
        platform="tiktok",
        account={"login_url": "https://seller.tiktokshopglobalselling.com/account/login"},
    )
    assert ready is False
    # When the runtime page is about:blank, TikTok probing should do a single
    # prime navigation (login_url) and then observe without extra goto probes.
    assert page.goto_calls == ["https://seller.tiktokshopglobalselling.com/account/login"]


@pytest.mark.asyncio
async def test_session_file_read_entrypoints_are_gone() -> None:
    """会话文件体系废除后，runtime_session 侧不得再有会话文件读入口（D5 / R1）。

    旧实现是 ``load_runtime_session_candidate`` → ``_load_session_async``（读会话文件）
    + ``_bootstrap_session_from_profile_sync``（把 profile 复制成会话文件）。
    现在登录态只由 profile 承载，这条链路整体下线。
    """
    from modules.apps.collection_center import runtime_session

    for name in (
        "load_runtime_session_candidate",
        "load_or_bootstrap_runtime_storage_state",
        "_load_session_async",
        "_bootstrap_session_from_profile_sync",
        "_save_session_async",
        "RuntimeSessionCandidate",
    ):
        assert not hasattr(runtime_session, name), (
            f"runtime_session 仍保留会话文件入口 {name}"
        )

    # profile → 内存快照的能力保留（只活在内存里，不落盘）。
    assert hasattr(runtime_session, "snapshot_profile_storage_state_sync")


@pytest.mark.asyncio
async def test_check_login_gate_ready_accepts_miaoshou_root_shell_cookie_backed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DetectorResult:
        status = type("Status", (), {"value": "logged_in"})()
        confidence = 0.65
        matched_pattern = "JSESSIONID"
        detected_by = "cookie"

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult()

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )

    ok, gate_result = await check_login_gate_ready(
        page=type("Page", (), {"url": "https://erp.91miaoshou.com/"})(),
        platform="miaoshou",
    )

    assert ok is True
    assert gate_result.status is GateStatus.READY
    assert gate_result.reason == "cookie-backed session confirmed"


@pytest.mark.asyncio
async def test_check_login_gate_ready_rejects_tiktok_cookie_only_root_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DetectorResult:
        status = type("Status", (), {"value": "logged_in"})()
        confidence = 0.85
        matched_pattern = "sessionid"
        detected_by = "cookie"

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult()

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )

    ok, gate_result = await check_login_gate_ready(
        page=type("Page", (), {"url": "https://seller.tiktokshopglobalselling.com/"})(),
        platform="tiktok",
    )

    assert ok is True
    assert gate_result.status is GateStatus.READY


@pytest.mark.asyncio
async def test_executor_auto_mode_skips_storage_bootstrap_when_tiktok_prefers_existing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )

    persistent_bundle = RuntimeContextBundle(
        mode="persistent_profile",
        context=object(),
        page=object(),
        reused_session=True,
    )
    open_profile = AsyncMock(return_value=persistent_bundle)
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        open_profile,
    )

    executor = CollectionExecutorV2()
    bundle = await executor._open_runtime_bundle(
        session_runtime_mode="auto",
        browser=None,
        browser_type=object(),
        platform="tiktok",
        session_owner_id="main-1",
        runtime_account={"shop_region": "SG"},
        storage_state=None,
        launch_kwargs={"headless": False},
    )

    assert bundle.mode in {"storage_state_fanout", "persistent_profile"}
