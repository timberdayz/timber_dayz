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
                "viewport": {"width": 1600, "height": 900},
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
async def test_open_storage_state_runtime_bundle_uses_new_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = object()
    new_context_kwargs: dict[str, object] = {}

    class _FakeContext:
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
    assert options["viewport"] is None


def test_build_runtime_login_gate_probe_urls_uses_homepage_then_login_url() -> None:
    urls = build_runtime_login_gate_probe_urls(
        platform="tiktok",
        account={"login_url": "https://seller.tiktok.com/account/login"},
    )

    assert urls == [
        "https://seller.tiktok.com/homepage",
        "https://seller.tiktok.com/account/login",
    ]


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


@pytest.mark.asyncio
async def test_probe_runtime_login_gate_checks_homepage_after_current_page_miss(
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
            (
                True,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.READY,
                    reason="homepage probe confirmed",
                    current_url="https://seller.tiktok.com/homepage",
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
        account={"login_url": "https://seller.tiktok.com/account/login"},
    )

    assert ready is True
    assert gate_result.reason == "homepage probe confirmed"
    assert page.goto_calls == ["https://seller.tiktok.com/homepage"]


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
