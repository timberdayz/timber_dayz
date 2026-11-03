"""Task 3.1: 账号会话锁后端判定**统一**(父进程与录制子进程同一个入口)。

问题
----
同一个主账号的持久 profile 目录**不能被两个进程同时打开**(Chromium 的
``SingletonLock``)。锁必须跨进程(Redis ``SET NX``)才有效。

但改造前两侧选后端的规则**不一样**:

* 父进程(FastAPI 采集任务)用 ``auto`` -> 「生产 → Redis, 其余 → 进程内锁」;
* 子进程(录制/组件测试 ``tools/test_component.py``)用另一套 -> 「配了
  ``REDIS_URL`` 就 Redis」。

-> 非生产环境下父进程拿**进程内锁**(只在同进程内互斥)、子进程拿 **Redis 锁**
-> 两者互相排斥不了 -> 采集任务正在用某账号的 profile 时, 录制照样能打开
同一个目录 -> 撞 Chromium 独占锁。

修法
----
两侧收敛到**同一个**判定入口
(``backend/services/main_account_session_lock.create_default_backend()``):

* ``redis``(显式) -> 强制 Redis, 拿不到按 fail-closed 分级;
* ``local``(显式) -> 进程内锁, **一个 Redis 连接都不建**;
* ``auto`` -> 生产 -> Redis; 非生产但**配置上指向了 Redis** -> 也走 Redis;
  未配 -> 进程内锁 + 明确告警。

本文件钉住「**两侧必须是同一个判定**」这个契约(防止再次分叉)。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, List

import pytest

from backend.services import main_account_session_lock as lock_module
from tools.test_component import ComponentTester

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_COMPONENT_PATH = REPO_ROOT / "tools" / "test_component.py"


def _tester() -> ComponentTester:
    return ComponentTester(platform="miaoshou", account_id="shop-1")


def _clear_redis_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """把「有没有配 Redis 地址」变成用例自己能控的变量。"""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)


def _install_fake_redis_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 Redis 客户端换成假的(单元测试**绝不**连真实 Redis)。"""

    async def _fake_client() -> Any:
        return object()

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)


# ---------------------------------------------------------------------------
# 父进程与子进程: 同一套环境变量 -> 同一种后端
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend_mode", "environment", "redis_configured", "expected"),
    [
        # auto + 非生产 + 配了 Redis 地址 -> 两侧都走 Redis(核心验收)
        ("auto", "development", True, "redis"),
        # auto + 非生产 + 未配 Redis 地址 -> 两侧都退化为进程内锁
        ("auto", "development", False, "local"),
        # auto + 生产 -> Redis(生产行为不变)
        ("auto", "production", True, "redis"),
        # 显式 redis -> 两侧都强制 Redis
        ("redis", "development", True, "redis"),
        # 显式 local -> 两侧都强制进程内锁
        ("local", "development", True, "local"),
    ],
)
async def test_parent_and_subprocess_choose_the_same_backend(
    monkeypatch: pytest.MonkeyPatch,
    backend_mode: str,
    environment: str,
    redis_configured: bool,
    expected: str,
) -> None:
    """同一套环境变量下, 父进程与录制子进程必须选到**同一种**后端。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", backend_mode)
    monkeypatch.setenv("ENVIRONMENT", environment)
    if redis_configured:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    else:
        _clear_redis_env(monkeypatch)
    _install_fake_redis_client(monkeypatch)

    parent_mode = lock_module.resolve_session_lock_backend_mode()
    parent_backend = await lock_module.create_default_backend()
    subprocess_backend = await _tester()._build_profile_session_lock_backend()

    assert parent_mode == expected
    assert isinstance(
        parent_backend,
        lock_module.RedisSessionLockBackend
        if expected == "redis"
        else lock_module.LocalSessionLockBackend,
    )
    assert isinstance(
        subprocess_backend,
        lock_module.RedisSessionLockBackend
        if expected == "redis"
        else lock_module.LocalSessionLockBackend,
    )


@pytest.mark.asyncio
async def test_parent_and_subprocess_use_the_same_lock_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两侧必须是**同一个 key 空间** -> 才谈得上「互相排斥」。"""
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    _install_fake_redis_client(monkeypatch)

    parent_key = lock_module.build_lock_key("miaoshou", "main-1")

    recorded: List[str] = []

    class _FakeLock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def acquire(self, platform: str, main_account_id: str, **kwargs: Any) -> Any:
            recorded.append(lock_module.build_lock_key(platform, main_account_id))
            raise RuntimeError("stop here")  # 只关心 key, 不真的去抢锁

    monkeypatch.setattr(lock_module, "MainAccountSessionLock", _FakeLock)

    tester = _tester()
    with pytest.raises(RuntimeError):
        await tester._acquire_profile_session_lock(main_account_id="main-1")

    assert recorded == [parent_key]


# ---------------------------------------------------------------------------
# 防复发: 子进程不得再自带一套后端判定
# ---------------------------------------------------------------------------


def _find_function(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == name
        ):
            return node
    raise AssertionError(f"未找到函数: {name}")


def test_subprocess_backend_builder_delegates_to_the_shared_entry() -> None:
    """子进程的后端构建必须**调用**统一入口, 而不是自己判一遍。"""
    tree = ast.parse(
        TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")
    )
    function = _find_function(tree, "_build_profile_session_lock_backend")

    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "create_default_backend" in called


def _code_strings_and_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """收集**代码里**(不含 docstring)的字符串常量与标识符。

    docstring 里可以写「规则说明」, 但**代码**里不许再出现自己的判定逻辑 ——
    否则子进程就会再次分叉。
    """
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    strings: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                strings.add(node.value)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return strings, names


def test_subprocess_does_not_reimplement_backend_selection() -> None:
    """子进程**不得**再出现自己的后端判定(否则会再次分叉)。"""
    tree = ast.parse(
        TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")
    )
    strings, names = _code_strings_and_names(tree)

    # 判定相关的标识符: 一律不许在子进程代码里出现
    for forbidden in (
        "account_session_lock_environment",
        "account_session_lock_backend",
        "account_session_lock_redis_configured",
        "get_shared_redis_client",
        "get_local_session_lock_backend",
        "RedisSessionLockBackend",
        "MainAccountSessionLockUnavailableError",
    ):
        assert forbidden not in names, f"子进程不得再自带后端判定: {forbidden}"

    # 判定相关的环境变量名: 一律不许在子进程代码里出现
    for forbidden in ("REDIS_URL", "ACCOUNT_SESSION_LOCK_BACKEND", "CELERY_BROKER_URL"):
        assert forbidden not in strings, f"子进程不得再自带后端判定: {forbidden}"
