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

评审修复覆盖点：
- F1 重开持久 context 后的页面必须被导航到平台入口（不能停在 about:blank）
- F5 旧/有头 context 关闭失败必须中止回退（不能撞 Chromium profile 独占锁）
- F6 有头 context 的关闭必须发生在重开之前
- F12 「不写会话文件」的断言范围只覆盖回退函数内部
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center import executor_v2 as executor_v2_module
from modules.apps.collection_center import runtime_session
from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
    StepExecutionError,
)
from backend.services.platform_login_entry_service import get_platform_login_entry


#: shopee 的平台标准入口（回归点 F1：重开后的页面必须导航到这里）
SHOPEE_LOGIN_ENTRY = get_platform_login_entry("shopee")


class _FakePage:
    """最小 page 替身（没有 goto → prime_runtime_page_for_login_gate 直接返回）。"""

    def __init__(self) -> None:
        self.url = "https://example.com/login"

    async def close(self) -> None:
        return None


class _NavigablePage:
    """支持 goto 的 page 替身。

    默认首屏是 ``about:blank`` —— 这正是 Playwright 启动**持久 context** 时的真实
    行为（``chromium.js``: ``if (isPersistent) chromeArguments.push("about:blank")``）。
    """

    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
        return None

    async def wait_for_timeout(self, ms: int) -> None:
        return None

    async def close(self) -> None:
        return None


class _FakePersistentContext:
    """模拟 launch_persistent_context 返回的**持久 context**。"""

    def __init__(
        self,
        user_data_dir: str,
        events: list[str],
        *,
        page_factory=None,
        close_error: Exception | None = None,
    ) -> None:
        self.user_data_dir = user_data_dir
        self.events = events
        self.pages: list[_FakePage] = []
        self.closed = False
        self._page_factory = page_factory or _FakePage
        self._close_error = close_error

    async def new_page(self) -> _FakePage:
        page = self._page_factory()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.events.append(f"close:{self.user_data_dir}")
        if self._close_error is not None:
            raise self._close_error
        self.closed = True


class _FakeBrowserType:
    """模拟 Playwright BrowserType：只提供持久 context 入口。"""

    def __init__(
        self,
        events: list[str],
        *,
        page_factory=None,
        fail_close_on_launch: int | None = None,
    ) -> None:
        self.events = events
        self.launch_calls: list[dict] = []
        self.contexts: list[_FakePersistentContext] = []
        self._page_factory = page_factory
        self._fail_close_on_launch = fail_close_on_launch

    async def launch_persistent_context(self, **kwargs):
        self.launch_calls.append(dict(kwargs))
        user_data_dir = str(kwargs.get("user_data_dir") or "")
        self.events.append(f"launch_persistent:{user_data_dir}")
        # 模拟 Chromium 在 profile 目录里落盘
        profile_dir = Path(user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "Cookies").write_text("[]", encoding="utf-8")
        close_error = None
        if self._fail_close_on_launch == len(self.launch_calls) - 1:
            close_error = RuntimeError(
                "Target page, context or browser has been closed"
            )
        context = _FakePersistentContext(
            user_data_dir,
            self.events,
            page_factory=self._page_factory,
            close_error=close_error,
        )
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


class _FailingCloseContext:
    """close() 抛异常：模拟旧 Chromium 没退干净（仍占用 profile 目录）。"""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    async def close(self) -> None:
        self.events.append("close-failed:old_context")
        raise RuntimeError("Target page, context or browser has been closed")


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
        self.warning_messages: list[str] = []

    def debug(self, msg, *args, **kwargs) -> None:
        self.debug_messages.append(str(msg) % args if args else str(msg))

    def info(self, msg, *args, **kwargs) -> None:
        return None

    def warning(self, msg, *args, **kwargs) -> None:
        self.warning_messages.append(str(msg) % args if args else str(msg))


# ---------------------------------------------------------------------------
# legacy 回退路径的替身（没有持久化 profile 目标时走这条分支）
# ---------------------------------------------------------------------------


class _FakeLegacyContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.pages: list[_FakePage] = []

    async def new_page(self) -> _FakePage:
        page = _FakePage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.events.append("close:legacy_context")


class _FakeLegacyBrowser:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.context_kwargs: dict = {}

    async def new_context(self, **kwargs):
        self.context_kwargs.update(kwargs)
        self.events.append("new_context")
        return _FakeLegacyContext(self.events)

    async def close(self) -> None:
        self.events.append("close:legacy_browser")


class _FakeChromium:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.launched: list[dict] = []

    async def launch(self, **kwargs):
        self.launched.append(kwargs)
        return _FakeLegacyBrowser(self.events)


class _FakePlaywrightManager:
    def __init__(self, chromium) -> None:
        self._chromium = chromium

    async def __aenter__(self):
        return type("PW", (), {"chromium": self._chromium})()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _install_legacy_playwright(monkeypatch, events: list[str]) -> _FakeChromium:
    chromium = _FakeChromium(events)
    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: _FakePlaywrightManager(chromium),
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
    return chromium


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
        launch_kwargs=(
            launch_kwargs if launch_kwargs is not None else {"headless": True}
        ),
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
async def test_headful_fallback_returns_persistent_context(
    monkeypatch, profile_runtime
):
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
    """回退**本函数内**不得写 data/sessions（profile 是唯一载体，R1/R2）。

    覆盖范围说明（评审 F12）：本用例只调用 ``_run_headful_login_fallback``，
    因此它钉住的是「**回退函数内部**不写会话文件」。
    Task 7 之后会话文件体系整体废除：executor 侧连会话文件写入口本身
    都不存在了（``_save_session_async`` 已删除）。
    """
    from modules.apps.collection_center import executor_v2

    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    assert not hasattr(executor_v2, "_save_session_async"), "会话文件写入口仍存在"

    await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    assert profile_runtime.session_saves == []


@pytest.mark.asyncio
async def test_headful_fallback_context_options_have_no_fingerprint_overrides(
    monkeypatch,
    profile_runtime,
):
    """R8（2026-11-14 修订）：profile 路径**不叠加** locale / timezone_id 覆盖；
    UA 只在 **headless** 那一次注入（去掉 ``HeadlessChrome``）。

    这条回退路径开两次浏览器：① **有头**人工验证码（UA 本来就正常 ⇒ 不碰）；
    ② 人工登录完成后**按原参数重开**（headless ⇒ 必须去掉 ``HeadlessChrome``，
    否则平台一眼认出自动化）。
    """
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

    assert browser_type.launch_calls, "回退必须至少开一次浏览器"
    for call in browser_type.launch_calls:
        if call.get("headless"):
            # headless ⇒ UA 去掉 HeadlessChrome（版本与 OS token 取自真实浏览器）
            assert "HeadlessChrome" not in call["user_agent"]
            assert call["user_agent"].startswith("Mozilla/5.0 (")
        else:
            # headful ⇒ UA 本来就正常 ⇒ 不覆盖
            assert "user_agent" not in call
        # locale / 时区不覆盖（沿用 profile 原生环境）
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
    """R6：旧 context 必须先 close，否则同一 profile 目录 ProcessSingleton 冲突。

    评审 F6：不仅要断言「旧 context 先关」，还要钉住**有头 context 的关闭发生在
    重开之前** —— 否则有人把 headed close 挪到重开之后，两条断言仍然成立，
    但运行时会在同一 profile 目录上同时开两个持久 context。
    """
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
    # 有头 context 必须在**重开之前**关闭
    assert events[2].startswith("close:")
    assert events[3] == f"launch_persistent:{profile_runtime.profile_dir}"
    # 全局顺序：所有 close 事件都必须早于最后一次 launch_persistent
    close_indexes = [i for i, event in enumerate(events) if event.startswith("close:")]
    last_launch_index = max(
        i for i, event in enumerate(events) if event.startswith("launch_persistent:")
    )
    assert close_indexes, "回退过程必须有关闭事件"
    assert max(close_indexes) < last_launch_index


@pytest.mark.asyncio
async def test_headful_fallback_reopened_page_is_navigated_to_platform_entry(
    monkeypatch,
    profile_runtime,
):
    """评审 F1：重开持久 context 后的页面必须被导航到平台入口。

    Playwright 启动持久 context 时 push 的首屏是 ``about:blank`` → 登录态探测只能
    给 UNKNOWN → 闸门 READY 要求 logged_in + 置信度 >= 0.7 → **必然失败**，
    而且报错只说 ``url=about:blank``，完全指不到真因。
    """
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events, page_factory=_NavigablePage)

    result = await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    _login_success, _context, page, _outcome = result
    assert page.goto_calls, "重开后的页面必须被导航到平台入口"
    assert page.url != "about:blank"
    assert page.goto_calls[0] == SHOPEE_LOGIN_ENTRY
    assert page.url == SHOPEE_LOGIN_ENTRY


@pytest.mark.asyncio
async def test_headful_fallback_navigates_platform_entry_even_when_previous_tab_restored(
    monkeypatch,
    profile_runtime,
):
    """评审 F1 的另一半：Chromium 恢复上次会话标签页时也必须导航。

    评审未能实测「干净关闭后重开」Chromium 是否恢复标签页，所以修法必须两种情况
    都成立：**无论当前 URL 是不是 about:blank**，都要确保页面被导航到平台入口
    （恢复的标签页未必是平台页，同样会让闸门误判）。
    """
    executor = _build_executor(monkeypatch)
    events: list[str] = []

    def _restored_tab_page() -> _NavigablePage:
        # 模拟 Chromium 恢复了上次会话的标签页（非平台页）
        return _NavigablePage("https://example.com/previous-tab")

    browser_type = _FakeBrowserType(events, page_factory=_restored_tab_page)

    result = await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    _login_success, _context, page, _outcome = result
    assert page.goto_calls, "非 about:blank 的恢复标签页也必须被导航到平台入口"
    assert page.goto_calls[0] == SHOPEE_LOGIN_ENTRY
    assert page.url == SHOPEE_LOGIN_ENTRY


@pytest.mark.asyncio
async def test_headful_fallback_page_navigation_failure_does_not_crash_fallback(
    monkeypatch,
    profile_runtime,
):
    """评审 F1：导航失败**不能**让流程崩成看不懂的错（要有清晰中文日志）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    recording_logger = _RecordingLogger()
    monkeypatch.setattr(executor_v2_module, "logger", recording_logger)

    class _BrokenGotoPage(_NavigablePage):
        async def goto(self, url: str, **kwargs) -> None:
            raise TimeoutError("page.goto: Timeout 60000ms exceeded")

    browser_type = _FakeBrowserType(events, page_factory=_BrokenGotoPage)

    result = await _run_profile_fallback(
        executor,
        browser_type=browser_type,
        profile_dir=profile_runtime.profile_dir,
        old_context=_OldContext(events),
        browser=_ForbiddenBrowser(),
    )

    login_success, _context, _page, outcome = result
    assert login_success is True
    assert outcome == "success"
    assert any(
        "导航到平台入口失败" in message for message in recording_logger.warning_messages
    )


@pytest.mark.asyncio
async def test_headful_fallback_aborts_when_old_context_close_fails(
    monkeypatch,
    profile_runtime,
):
    """评审 F5：旧 context 关不掉必须**中止回退**（否则撞 Chromium 独占锁）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(events)

    with pytest.raises(StepExecutionError, match="profile 独占锁冲突"):
        await _run_profile_fallback(
            executor,
            browser_type=browser_type,
            profile_dir=profile_runtime.profile_dir,
            old_context=_FailingCloseContext(events),
            browser=_ForbiddenBrowser(),
        )

    # 旧 context 没关掉 → 绝不能再开持久 context
    assert browser_type.launch_calls == []


@pytest.mark.asyncio
async def test_headful_fallback_aborts_when_headed_context_close_fails(
    monkeypatch,
    profile_runtime,
):
    """评审 F5：有头 context 关不掉也必须中止（登录态可能没刷盘 + 独占锁冲突）。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    browser_type = _FakeBrowserType(
        events,
        fail_close_on_launch=0,
    )

    with pytest.raises(StepExecutionError, match="profile 独占锁冲突"):
        await _run_profile_fallback(
            executor,
            browser_type=browser_type,
            profile_dir=profile_runtime.profile_dir,
            old_context=_OldContext(events),
            browser=_ForbiddenBrowser(),
        )

    # 有头 context 没关掉 → 绝不能重开同一 profile 目录
    assert len(browser_type.launch_calls) == 1


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


@pytest.mark.asyncio
async def test_legacy_fallback_keeps_login_state_when_session_account_id_is_empty(
    monkeypatch,
    profile_runtime,
):
    """评审 F3：session_account_id 为空时**也必须**把登录态交给主 context。

    旧写法只看 ``session_account_id`` → 它为空时整份登录态被丢弃 → 主 context
    以完全未登录的状态继续采集（后续 401 / 跳登录页 / 结果为空）。
    """
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    _install_legacy_playwright(monkeypatch, events)

    captured: list[tuple[str, str]] = []
    storage_state = {"cookies": [{"name": "sid", "value": "v"}]}

    async def _fake_capture(*, page, session_platform, session_account_id):
        captured.append((session_platform, session_account_id))
        return dict(storage_state)

    executor._wait_and_capture_high_quality_tiktok_session = _fake_capture

    main_browser = _FakeLegacyBrowser(events)

    result = await executor._run_headful_login_fallback(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1"},
        params={"params": {}},
        browser=main_browser,
        old_context=_OldContext(events),
        session_platform="shopee",
        session_account_id="",
        runtime_manifests={"login": {"component": "login"}},
        proxy=None,
        browser_type=None,
        profile_path=None,
        launch_kwargs={"headless": True},
    )

    login_success, _context, _page, outcome = result
    assert login_success is True
    assert outcome == "success"
    # 采集必须发生，且用的是已解析好的 account_id
    assert captured == [("shopee", "acc-1")]
    # 主 context 必须带上登录态（否则等于未登录采集）
    assert main_browser.context_kwargs.get("storage_state") == storage_state


@pytest.mark.asyncio
async def test_legacy_fallback_fails_loudly_when_login_state_cannot_be_captured(
    monkeypatch,
    profile_runtime,
):
    """评审 F3：拿不到登录态必须**显式报错**，不能静默造一个未登录的 context。"""
    executor = _build_executor(monkeypatch)
    events: list[str] = []
    _install_legacy_playwright(monkeypatch, events)

    async def _fake_capture(*, page, session_platform, session_account_id):
        return None

    executor._wait_and_capture_high_quality_tiktok_session = _fake_capture

    main_browser = _FakeLegacyBrowser(events)

    with pytest.raises(StepExecutionError, match="未能取到登录态快照"):
        await executor._run_headful_login_fallback(
            task_id="task-1",
            platform="shopee",
            account={"account_id": "acc-1"},
            params={"params": {}},
            browser=main_browser,
            old_context=_OldContext(events),
            session_platform="shopee",
            session_account_id="",
            runtime_manifests={"login": {"component": "login"}},
            proxy=None,
            browser_type=None,
            profile_path=None,
            launch_kwargs={"headless": True},
        )

    # 绝不能造一个「没有 storage_state」的未登录 context 继续跑
    assert "storage_state" not in main_browser.context_kwargs
