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
    profile_path.mkdir(parents=True)
    (profile_path / "Preferences").write_text("{}", encoding="utf-8")

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
    assert launch_kwargs["locale"] == "zh-CN"
    assert launch_kwargs["accept_downloads"] is True


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

    assert urls == []


def test_build_runtime_login_gate_probe_urls_skips_region_scoped_homepage_for_tiktok() -> None:
    urls = build_runtime_login_gate_probe_urls(
        platform="tiktok",
        account={
            "login_url": "https://seller.tiktokshopglobalselling.com/account/login",
            "shop_region": "SG",
        },
    )

    assert urls == []


def test_formal_sequential_runtime_prefers_storage_state_when_available() -> None:
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

    assert decision.mode == "storage_state_fanout"
    assert decision.reason == "storage_state_available"
    assert decision.used_storage_state is True
    assert decision.used_persistent_profile is False


def test_formal_sequential_runtime_allows_preferring_persistent_profile_for_tiktok_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TIKTOK_RUNTIME_PREFER_PERSISTENT_PROFILE", "true")

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
    assert decision.used_persistent_profile is True
    assert decision.used_storage_state is False


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

    results = iter(
        [
            (
                False,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.FAILED,
                    reason="current page inconclusive",
                    current_url="https://seller.tiktok.com/some-other-page",
                ),
            ),
        ]
    )

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.check_login_gate_ready",
        AsyncMock(side_effect=lambda **kwargs: next(results)),
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
    assert gate_result.reason == "current page inconclusive"
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
    assert page.goto_calls == ["https://seller.tiktokshopglobalselling.com/"]


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

    assert ok is False
    assert gate_result.status is GateStatus.FAILED
    assert gate_result.reason == "tiktok page readiness not confirmed"


@pytest.mark.asyncio
async def test_executor_auto_mode_skips_storage_bootstrap_when_tiktok_prefers_existing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    monkeypatch.setenv("TIKTOK_RUNTIME_PREFER_PERSISTENT_PROFILE", "true")
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )

    async def _unexpected_bootstrap(**kwargs):
        raise AssertionError("storage bootstrap should not run before persistent profile")

    persistent_bundle = RuntimeContextBundle(
        mode="persistent_profile",
        context=object(),
        page=object(),
        reused_session=True,
    )

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.load_or_bootstrap_runtime_storage_state",
        _unexpected_bootstrap,
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

    assert bundle is persistent_bundle
    open_profile.assert_awaited_once()
