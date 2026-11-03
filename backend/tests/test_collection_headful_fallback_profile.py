"""有头人工验证码回退必须走持久化 profile（Task 4.5）。

规范依据（docs/guides/COLLECTION_SESSION_LIFECYCLE.md）：
- R1 真相源唯一：profile 是唯一的权威登录态载体，不再有第二份副本
- R2 登录即持久：应用层不执行任何"保存会话"动作
- R6 账号级串行：同一 profile 目录不能被两个浏览器进程同时打开
- R7 正常关闭才能落盘
- R8 指纹沿用 profile 原生环境（不注入 UA/locale/时区）

覆盖的回归点：
- H1 回退后的主 context 必须仍是**持久 context**（不是 browser.new_context）
- H2 回退路径不得注入全量指纹
- H3 回退不得再"读会话文件 → 二次开同一 profile 目录"
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center import executor_v2 as executor_v2_module
from modules.apps.collection_center import runtime_session
from modules.apps.collection_center.executor_v2 import CollectionExecutorV2


class _FakePage:
    """最小 page 替身（没有 goto → prime_runtime_page_for_login_gate 直接返回）。"""

    def __init__(self) -> None:
        self.url = "https://example.com/login"

    async def close(self) -> None:
        return None


class _FakePersistentContext:
    """模拟 launch_persistent_context 返回的**持久 context**。"""

    def __init__(self, user_data_dir: str, events: list[str]) -> None:
        self.user_data_dir = user_data_dir
        self.events = events
        self.pages: list[_FakePage] = []
        self.closed = False

    async def new_page(self) -> _FakePage:
        page = _FakePage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True
        self.events.append(f"close:{self.user_data_dir}")


class _FakeBrowserType:
    """模拟 Playwright BrowserType：只提供持久 context 入口。"""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.launch_calls: list[dict] = []
        self.contexts: list[_FakePersistentContext] = []

    async def launch_persistent_context(self, **kwargs):
        self.launch_calls.append(dict(kwargs))
        user_data_dir = str(kwargs.get("user_data_dir") or "")
        self.events.append(f"launch_persistent:{user_data_dir}")
        # 模拟 Chromium 在 profile 目录里落盘
        profile_dir = Path(user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "Cookies").write_text("[]", encoding="utf-8")
        context = _FakePersistentContext(user_data_dir, self.events)
        self.contexts.append(context)
        return context


class _OldContext:
    """回退前的旧主 context：必须先被 close，否则 Chromium ProcessSingleton 冲突。"""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        self.events.append("close:old_context")


class _ForbiddenBrowser:
    """profile 路径下不允许再出现 browser.new_context（那是 H1 的根因）。"""

    def __init__(self) -> None:
        self.new_context_calls = 0

    async def new_context(self, **kwargs):
        self.new_context_calls += 1
        raise AssertionError("profile 回退路径不允许使用 browser.new_context")

    async def close(self) -> None:
        return None


class _RecordingLogger:
    def __init__(self) -> None:
        self.debug_messages: list[str] = []

    def debug(self, msg, *args, **kwargs) -> None:
        self.debug_messages.append(str(msg) % args if args else str(msg))

    def info(self, msg, *args, **kwargs) -> None:
        return None

    def warning(self, msg, *args, **kwargs) -> None:
        return None


@pytest.fixture
def profile_runtime(monkeypatch, tmp_path):
    """把 runtime_session 的外部依赖换成可控替身（不碰仓库里的 profiles 目录）。"""
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    fingerprint_options = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fake/1.0",
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "viewport": {"width": 2880, "height": 1800},
        "accept_downloads": True,
    }

    async def _fake_build_runtime_context_options(**kwargs):
        return dict(fingerprint_options)

    monkeypatch.setattr(
        runtime_session,
        "build_runtime_context_options",
        _fake_build_runtime_context_options,
    )

    session_saves: list[tuple] = []

    class _FakeSessionManager:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_persistent_profile_path(self, platform, account_id):
            return profile_dir

        def save_session(self, *args, **kwargs):
            session_saves.append((args, kwargs))
            return True

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager",
        _FakeSessionManager,
    )

    return SimpleNamespace(
        profile_dir=profile_dir,
        fingerprint_options=fingerprint_options,
        session_saves=session_saves,
    )


def _build_executor(monkeypatch) -> CollectionExecutorV2:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor._ensure_login_gate_ready = AsyncMock()
    executor._run_runtime_manifest_component = AsyncMock(
        return_value=SimpleNamespace(success=True)
    )
    return executor


async def _run_profile_fallback(
    executor: CollectionExecutorV2,
    *,
    browser_type,
    profile_dir: Path,
    old_context,
    proxy=None,
    launch_kwargs=None,
    browser=None,
):
    return await executor._run_headful_login_fallback(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1"},
        params={"params": {}},
        browser=browser,
        old_context=old_context,
        session_platform="shopee",
        session_account_id="acc-1",
        runtime_manifests={"login": {"component": "login"}},
        proxy=proxy,
        browser_type=browser_type,
        profile_path=str(profile_dir),
        launch_kwargs=launch_kwargs if launch_kwargs is not None else {"headless": True},
    )


@pytest.mark.asyncio
async def test_headful_fallback_opens_headed_persistent_context_on_profile_dir(
    monkeypatch,
    profile_runtime,
):
    """回退必须开 launch_persistent_context(user_data_dir=profile, headless=False)。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)
    old_context = _OldContext(events)
    forbidden_browser = _ForbiddenBrowser()

    result = await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=old_context,
        browser=forbidden_browser,
    )

    assert len(result) == 4
    login_success, _context, _page, outcome = result
    assert login_success is True
    assert outcome == "success"

    assert len(browser_type.launch_calls) == 2
    headed_call = browser_type.launch_calls[0]
    assert headed_call["user_data_dir"] == str(profile_runtime.profile_dir)
    assert headed_call["headless"] is False
    # 重开阶段保持与主流程一致（headless）
    assert browser_type.launch_calls[1]["user_data_dir"] == str(
        profile_runtime.profile_dir
    )
    assert browser_type.launch_calls[1]["headless"] is True
    # 绝不能回退到 browser.new_context
    assert forbidden_browser.new_context_calls == 0


@pytest.mark.asyncio
async def test_headful_fallback_returns_persistent_context(monkeypatch, profile_runtime):
    """回退返回的新 context 必须仍是持久 context（修 H1）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    result = await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    _login_success, new_context, _page, _outcome = result
    assert isinstance(new_context, _FakePersistentContext)
    assert new_context is browser_type.contexts[-1]
    assert new_context.closed is False


@pytest.mark.asyncio
async def test_headful_fallback_does_not_write_session_files(
    monkeypatch,
    profile_runtime,
):
    """回退全程不得写 data/sessions（profile 是唯一载体，R1/R2）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    saved: list[tuple] = []

    async def _fake_save_session_async(*args, **kwargs):
        saved.append((args, kwargs))
        return True

    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._save_session_async",
        _fake_save_session_async,
    )

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    assert saved == []
    assert profile_runtime.session_saves == []


@pytest.mark.asyncio
async def test_headful_fallback_context_options_have_no_fingerprint_overrides(
    monkeypatch,
    profile_runtime,
):
    """R8：profile 路径不得注入 user_agent / locale / timezone_id（修 H2）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    for call in browser_type.launch_calls:
        assert "user_agent" not in call
        assert "locale" not in call
        assert "timezone_id" not in call
        # viewport 仍然保留（不是指纹覆盖项）
        assert call["viewport"] == {"width": 2880, "height": 1800}


@pytest.mark.asyncio
async def test_headful_fallback_passes_proxy_verbatim(monkeypatch, profile_runtime):
    """proxy 必须原样透传（含凭据），绝不能从已 strip 的 account 重解析。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)
    proxy = {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        proxy=proxy,
        browser=_ForbiddenBrowser(),
    )

    for call in browser_type.launch_calls:
        assert call["proxy"] == proxy


@pytest.mark.asyncio
async def test_headful_fallback_closes_old_context_before_opening_headed_profile(
    monkeypatch,
    profile_runtime,
):
    """R6：旧 context 必须先 close，否则同一 profile 目录 ProcessSingleton 冲突。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)
    old_context = _OldContext(events)

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=old_context,
        browser=_ForbiddenBrowser(),
    )

    assert old_context.closed is True
    assert events[0] == "close:old_context"
    assert events[1] == f"launch_persistent:{profile_runtime.profile_dir}"


@pytest.mark.asyncio
async def test_headful_fallback_leaves_chromium_writes_in_profile_dir(
    monkeypatch,
    profile_runtime,
):
    """headed 阶段结束后 profile 目录仍在，且有 Chromium 写入痕迹（R7 正常关闭）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    assert profile_runtime.profile_dir.exists()
    assert (profile_runtime.profile_dir / "Cookies").exists()
    # 有头阶段必须正常 close（R7：正常关闭才能落盘）
    assert browser_type.contexts[0].closed is True


@pytest.mark.asyncio
async def test_headful_fallback_legacy_path_without_profile_target(
    monkeypatch,
    profile_runtime,
):
    """profile 目标不可用时走 legacy 兜底路径，且不抛异常。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    recording_logger = _RecordingLogger()
    monkeypatch.setattr(executor_v2_module, "logger", recording_logger)

    launched: list[dict] = []
    context_kwargs: dict = {}

    class _FakeLegacyContext:
        def __init__(self) -> None:
            self.pages: list[_FakePage] = []

        async def new_page(self) -> _FakePage:
            page = _FakePage()
            self.pages.append(page)
            return page

        async def close(self) -> None:
            events.append("close:legacy_context")

    class _FakeLegacyBrowser:
        async def new_context(self, **kwargs):
            context_kwargs.update(kwargs)
            events.append("new_context")
            return _FakeLegacyContext()

        async def close(self) -> None:
            events.append("close:legacy_browser")

    class _FakeChromium:
        async def launch(self, **kwargs):
            launched.append(kwargs)
            return _FakeLegacyBrowser()

    class _FakePlaywright:
        chromium = _FakeChromium()

    class _FakePlaywrightManager:
        async def __aenter__(self):
            return _FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: _FakePlaywrightManager(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2."
        "_get_fingerprint_context_options_async",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 1280, "height": 800},
                "accept_downloads": True,
            }
        ),
    )
    executor._wait_and_capture_high_quality_tiktok_session = AsyncMock(
        return_value={"cookies": []}
    )

    result = await executor._run_headful_login_fallback(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1"},
        params={"params": {}},
        browser=_FakeLegacyBrowser(),
        old_context=_OldContext(events),
        session_platform="shopee",
        session_account_id="acc-1",
        runtime_manifests={"login": {"component": "login"}},
        proxy=None,
        browser_type=None,
        profile_path=None,
        launch_kwargs={"headless": True},
    )

    assert len(result) == 4
    login_success, _context, _page, outcome = result
    assert login_success is True
    assert outcome == "success"
    # 旧路径确实被走到（独立有头浏览器）
    assert launched and launched[0]["headless"] is False
    assert any("legacy" in message for message in recording_logger.debug_messages)
    # legacy 路径同样不写会话文件
    assert profile_runtime.session_saves == []


def test_executor_no_longer_has_session_file_recreation_helper():
    """回归护栏：会话文件中转（读会话文件 → browser.new_context）必须彻底消失。"""
    assert not hasattr(
        CollectionExecutorV2,
        "_recreate_runtime_page_with_saved_session",
    )
