"""Task 6.5：录制/组件测试子进程的 profile 身份与跨进程账号会话锁。

背景
----
目标架构是「**Chromium 持久化 profile 目录是登录态的唯一载体**」, profile 目录
统一按**主账号**命名(``profiles/<平台>/<主账号ID>``)。录制/组件测试子进程
(``tools/test_component.py``)必须与采集侧落在**同一个**目录, 否则录制时登录的
登录态采集永远读不到。

本文件覆盖三件事:

1. profile 目录身份 = **主账号 ID**(显式优先级链, 防回退到店铺账号 ID);
2. 打开**真实** profile 目录时持有**跨进程**账号会话锁(与采集侧同一个 key),
   临时目录不加锁; 锁服务不可用时**明确报错**(而不是让 Chromium 抛
   ProcessSingleton 天书错误);
3. ``tools/test_component.py`` 里不再有硬编码本机绝对路径的调试写入 ——
   那类代码在别的机器上会直接抛 ``FileNotFoundError`` 打崩子进程。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from backend.services import main_account_session_lock as lock_module
from backend.services.main_account_session_lock import (
    MainAccountSessionLockUnavailableError,
)
from tools.test_component import ComponentTester

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_COMPONENT_PATH = REPO_ROOT / "tools" / "test_component.py"

#: 盘符绝对路径(``C:\\...`` / ``f:/...``)与 UNC 路径 —— 换机器就必炸。
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")

#: 遗留 agent 调试写入的落盘路径。
_DEBUG_LOG_RE = re.compile(r"\.cursor[\\/]debug\.log")


def _tester(account_id: str = "shop-1") -> ComponentTester:
    return ComponentTester(platform="miaoshou", account_id=account_id)


class _FakeLockContextManager:
    """假的账号会话锁 context manager。"""

    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> None:
        self.entered += 1
        return None

    async def __aexit__(self, *exc_info: Any) -> bool:
        self.exited += 1
        return False


# ---------------------------------------------------------------------------
# ① profile 身份 = 主账号 ID
# ---------------------------------------------------------------------------


def test_profile_identity_prefers_main_account_id() -> None:
    """account_info 里有 main_account_id 时, profile 身份必须是它。"""
    tester = _tester(account_id="shop-1")

    identity = tester._resolve_profile_identity(
        {"main_account_id": "main-1", "account_id": "shop-1"}
    )

    assert identity == "main-1"


def test_profile_identity_falls_back_when_main_account_id_is_empty_string() -> None:
    """main_account_id 是空串时必须当作「没有」-> 回退到 self.account_id。"""
    tester = _tester(account_id="shop-1")

    identity = tester._resolve_profile_identity(
        {"main_account_id": "", "account_id": "shop-1"}
    )

    assert identity == "shop-1"


def test_profile_identity_session_owner_id_has_highest_priority() -> None:
    """session_owner_id 是显式指定的主账号 ID -> 覆盖一切。"""
    tester = _tester(account_id="shop-1")

    identity = tester._resolve_profile_identity(
        {"main_account_id": "main-1", "account_id": "shop-1"},
        session_owner_id="main-explicit",
    )

    assert identity == "main-explicit"


def test_profile_identity_falls_back_to_account_info_account_id() -> None:
    """没有主账号、也没有构造参数账号时, 最后回退到 account_info 里的账号 ID。"""
    tester = _tester(account_id="")

    identity = tester._resolve_profile_identity({"account_id": "shop-9"})

    assert identity == "shop-9"


def test_profile_identity_defaults_when_nothing_is_available() -> None:
    tester = _tester(account_id="")

    assert tester._resolve_profile_identity(None) == "default"


def test_persistent_profile_path_uses_main_account_id() -> None:
    """profile 目录名 = 主账号 ID(与采集侧同一个目录)。"""
    from modules.utils.sessions.session_manager import SessionManager

    tester = _tester(account_id="shop-1")
    account_info = {"main_account_id": "main-1", "account_id": "shop-1"}

    identity = tester._resolve_profile_identity(account_info)
    profile_path = SessionManager().get_persistent_profile_path("miaoshou", identity)

    assert profile_path.name == "main-1"
    assert profile_path.parent.name == "miaoshou"


# ---------------------------------------------------------------------------
# ② 账号会话锁(跨进程)
# ---------------------------------------------------------------------------


def test_profile_lock_identity_only_for_reused_mode() -> None:
    """只有 reused(打开真实 profile 目录)才加锁; 临时目录不加锁。"""
    assert (
        ComponentTester._profile_session_lock_identity(
            persistent_context_mode="reused",
            session_owner_id="main-1",
        )
        == "main-1"
    )
    assert (
        ComponentTester._profile_session_lock_identity(
            persistent_context_mode="ephemeral",
            session_owner_id="main-1",
        )
        is None
    )
    assert (
        ComponentTester._profile_session_lock_identity(
            persistent_context_mode=None,
            session_owner_id="main-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_open_profile_session_lock_takes_lock_only_for_reused_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tester = _tester()
    acquired: List[str] = []

    async def _fake_acquire(*, main_account_id: str) -> Any:
        acquired.append(main_account_id)
        return _FakeLockContextManager()

    monkeypatch.setattr(tester, "_acquire_profile_session_lock", _fake_acquire)

    await tester._open_profile_session_lock(
        persistent_context_mode="reused",
        session_owner_id="main-1",
    )
    assert acquired == ["main-1"]

    acquired.clear()
    handle = await tester._open_profile_session_lock(
        persistent_context_mode="ephemeral",
        session_owner_id="main-1",
    )
    assert handle is None
    assert acquired == []


@pytest.mark.asyncio
async def test_acquired_lock_uses_same_key_space_as_collection_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """必须与采集侧是**同一把**锁(同 key 空间), 否则等于没锁。"""
    recorded: Dict[str, Any] = {}

    class _FakeLock:
        def __init__(self, backend: Any = None, **kwargs: Any) -> None:
            recorded["backend"] = backend
            recorded["kwargs"] = kwargs

        def acquire(
            self, platform: str, main_account_id: str, *, timeout: Optional[float] = None
        ) -> Any:
            recorded["platform"] = platform
            recorded["main_account_id"] = main_account_id
            recorded["key"] = lock_module.build_lock_key(platform, main_account_id)
            return _FakeLockContextManager()

    async def _fake_backend() -> Any:
        return object()

    tester = _tester()
    monkeypatch.setattr(lock_module, "MainAccountSessionLock", _FakeLock)
    monkeypatch.setattr(tester, "_build_profile_session_lock_backend", _fake_backend)

    await tester._acquire_profile_session_lock(main_account_id="main-1")

    assert recorded["platform"] == "miaoshou"
    assert recorded["main_account_id"] == "main-1"
    assert recorded["key"] == lock_module.build_lock_key("miaoshou", "main-1")


@pytest.mark.asyncio
async def test_lock_backend_uses_redis_when_mode_is_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    async def _fake_client() -> Any:
        return object()

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    backend = await _tester()._build_profile_session_lock_backend()

    assert isinstance(backend, lock_module.RedisSessionLockBackend)


@pytest.mark.asyncio
async def test_lock_backend_uses_redis_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    async def _fake_client() -> Any:
        return object()

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    backend = await _tester()._build_profile_session_lock_backend()

    assert isinstance(backend, lock_module.RedisSessionLockBackend)


@pytest.mark.asyncio
async def test_lock_backend_uses_redis_in_non_production_when_redis_url_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非生产环境: 进程内锁对**子进程**无效 -> 配了 REDIS_URL 就必须走 Redis。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    async def _fake_client() -> Any:
        return object()

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    backend = await _tester()._build_profile_session_lock_backend()

    assert isinstance(backend, lock_module.RedisSessionLockBackend)


@pytest.mark.asyncio
async def test_lock_backend_raises_when_redis_is_configured_but_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配了 Redis 却拿不到 -> 明确报错(中文), 而不是让 Chromium 报天书错误。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    async def _no_client() -> Any:
        return None

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _no_client)

    with pytest.raises(MainAccountSessionLockUnavailableError) as excinfo:
        await _tester()._build_profile_session_lock_backend()

    message = str(excinfo.value)
    assert "账号会话锁服务不可用" in message
    assert "profile" in message


@pytest.mark.asyncio
async def test_lock_backend_falls_back_to_local_without_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独立跑 CLI(没有 REDIS_URL) -> 进程内锁 + 明确告警, 不报错。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("REDIS_URL", raising=False)

    backend = await _tester()._build_profile_session_lock_backend()

    assert backend is lock_module.get_local_session_lock_backend()


@pytest.mark.asyncio
async def test_lock_backend_respects_explicit_local_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 local(测试护栏) -> 进程内锁, 绝不连真实 Redis。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "local")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    async def _boom() -> Any:  # pragma: no cover - 不应被调用
        raise AssertionError("显式 local 模式下不得连接 Redis")

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _boom)

    backend = await _tester()._build_profile_session_lock_backend()

    assert backend is lock_module.get_local_session_lock_backend()


@pytest.mark.asyncio
async def test_profile_lock_handle_release_is_idempotent() -> None:
    """放锁必须幂等(异常路径可能重复调用)。"""
    from tools.test_component import _ProfileSessionLockHandle

    cm = _FakeLockContextManager()
    handle = _ProfileSessionLockHandle(cm)

    await handle.release()
    await handle.release()

    assert cm.exited == 1
    assert handle.released is True


def _find_function(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == name
        ):
            return node
    raise AssertionError(f"未找到函数: {name}")


def _awaited_attribute_calls(node: ast.AST, attr: str) -> List[int]:
    """收集 `await xxx.<attr>()` 的行号。"""
    lines: List[int] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Await)
            and isinstance(child.value, ast.Call)
            and isinstance(child.value.func, ast.Attribute)
            and child.value.func.attr == attr
        ):
            lines.append(child.lineno)
    return lines


def test_profile_lock_is_released_after_context_close() -> None:
    """R7: 锁必须持有到持久 context **正常关闭之后**才放。

    Chromium 在 context 正常关闭时才把登录态刷盘; 先放锁会让另一个进程在
    Chromium 仍占用目录时打开它 -> ProcessSingleton 失败。
    """
    tree = ast.parse(
        TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")
    )
    function = _find_function(tree, "_test_with_browser")

    close_lines = _awaited_attribute_calls(function, "close")
    release_lines = _awaited_attribute_calls(function, "release")

    assert close_lines, "未找到 context.close() 调用"
    assert release_lines, "未找到账号会话锁释放调用"
    # 释放必须晚于**所有**关闭动作
    assert max(close_lines) < min(release_lines)

    # 释放必须放在 finally 里(异常路径也要放锁)
    finally_release_lines = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Try):
            for statement in node.finalbody:
                for child in ast.walk(statement):
                    if (
                        isinstance(child, ast.Await)
                        and isinstance(child.value, ast.Call)
                        and isinstance(child.value.func, ast.Attribute)
                        and child.value.func.attr == "release"
                    ):
                        finally_release_lines.add(child.lineno)
    assert set(release_lines) & finally_release_lines


# ---------------------------------------------------------------------------
# ③ 硬编码绝对路径的调试写入(防复发)
# ---------------------------------------------------------------------------


def _iter_open_calls(tree: ast.AST) -> List[ast.Call]:
    calls: List[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            calls.append(node)
    return calls


def test_test_component_has_no_absolute_path_open_calls() -> None:
    """全文件不得有「硬编码本机绝对路径」的 open() 写入。

    换一台机器(同事开发机 / 生产服务器)父目录不存在 -> ``FileNotFoundError``
    -> 直接打崩录制/组件测试子进程。
    """
    tree = ast.parse(
        TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")
    )

    offenders: List[str] = []
    for call in _iter_open_calls(tree):
        if not call.args:
            continue
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if _ABSOLUTE_PATH_RE.match(first.value):
                offenders.append(f"line {call.lineno}: {first.value}")

    assert offenders == []


def test_test_component_has_no_cursor_debug_log_reference() -> None:
    """遗留 agent 调试落盘路径(.cursor/debug.log)必须彻底消失。"""
    source = TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")

    assert _DEBUG_LOG_RE.search(source) is None
    assert "#region agent log" not in source
