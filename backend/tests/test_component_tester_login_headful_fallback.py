"""组件测试工具的**有头人工验证码回退**(Task 6.5 / F7)。

目标架构: **profile 是登录态的唯一载体**。因此这条回退必须与采集侧
(``CollectionExecutorV2._run_profile_headful_login_fallback``)同构:

* 在**同一个 profile 目录**上开有头持久 context(``launch_persistent_context``),
  登录态由 Chromium 自己写进 profile;
* 回退结束后**正常 close**(R7: Chromium 在 context 正常关闭时才刷盘);
* **不再有任何「写会话文件 -> 读会话文件」的中转**;
* 重开后**必须 prime 页面** —— 否则页面停在 ``about:blank``, 登录闸门
  (``LoginStatusDetector``)判定不了登录态(about:blank 上只能返回 UNKNOWN,
  置信度上限 0.59 < READY 门槛 0.7) -> 平台必然失败。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from tools.test_component import (
    ComponentTestResult,
    ComponentTester,
    HeadfulLoginFallbackRequired,
    TestStatus,
)

TEST_COMPONENT_PATH = Path(__file__).resolve().parents[2] / "tools" / "test_component.py"


class _FakeAdapter:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def login(self, page):  # noqa: ANN001
        raise self._exc


class _FakeBundle:
    def __init__(self, context: Any, page: Any) -> None:
        self.context = context
        self.page = page


class _FakeClosable:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


@pytest.mark.asyncio
async def test_component_tester_raises_headful_fallback_required_for_manual_continue_in_headless_mode():
    tester = ComponentTester(platform="tiktok", account_id="acc-1", headless=True)
    result = ComponentTestResult(
        component_name="login",
        platform="tiktok",
        status=TestStatus.PENDING,
    )

    adapter = _FakeAdapter(VerificationRequiredError("manual_intervention", "manual.png"))

    with pytest.raises(HeadfulLoginFallbackRequired) as exc_info:
        await tester._run_login_with_verification_support(
            adapter=adapter,
            page=object(),
            component_name="tiktok/login",
            result=result,
        )

    assert exc_info.value.verification_type == "manual_intervention"


@pytest.mark.asyncio
async def test_component_tester_run_login_before_non_login_uses_headful_fallback_result(
    monkeypatch: pytest.MonkeyPatch,
):
    tester = ComponentTester(platform="tiktok", account_id="acc-1", headless=True)
    result = ComponentTestResult(
        component_name="products_export",
        platform="tiktok",
        status=TestStatus.PENDING,
    )

    class _FakeSession:
        def close(self):
            return None

    monkeypatch.setattr("backend.models.database.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        "backend.services.component_version_service.ComponentVersionService.get_stable_version",
        lambda self, name: SimpleNamespace(file_path="modules/platforms/tiktok/components/login.py", id=1, version="1.0.0"),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.ComponentLoader.load_python_component_from_path",
        lambda self, *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.python_component_adapter.create_adapter",
        lambda *args, **kwargs: object(),
    )

    async def _raise_fallback(*args, **kwargs):  # noqa: ANN002, ANN003
        raise HeadfulLoginFallbackRequired("manual_intervention", "manual.png")

    new_context = object()
    new_page = object()

    monkeypatch.setattr(tester, "_run_login_with_verification_support", _raise_fallback)
    monkeypatch.setattr(
        tester,
        "_run_headful_login_fallback",
        AsyncMock(return_value=(True, new_context, new_page)),
    )

    ok, context, page = await tester._run_login_before_non_login(
        browser=object(),
        context=object(),
        page=object(),
        account_info={"account_id": "acc-1", "login_url": "https://seller.tiktokglobalshop.com"},
        result=result,
    )

    assert ok is True
    assert context is new_context
    assert page is new_page


# ---------------------------------------------------------------------------
# 回退实现: 同一 profile 目录 + 不写会话文件 + 重开后 prime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headful_fallback_uses_same_profile_dir_and_primes_reopened_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    tester = ComponentTester(platform="tiktok", account_id="shop-1", headless=True)
    account_info = {
        "account_id": "shop-1",
        "main_account_id": "main-1",
        "login_url": "https://seller.tiktokglobalshop.com",
    }
    profile_dir = tmp_path / "profiles" / "tiktok" / "main-1"

    opened: List[Dict[str, Any]] = []
    primed: List[Dict[str, Any]] = []
    saved_sessions: List[Any] = []

    async def _fake_open_persistent_runtime_bundle(**kwargs: Any) -> _FakeBundle:
        opened.append(kwargs)
        index = len(opened)
        return _FakeBundle(f"context-{index}", f"page-{index}")

    async def _fake_prime(*, page: Any, platform: str, account: Any) -> None:
        primed.append({"page": page, "platform": platform, "account": account})

    async def _fake_login(**kwargs: Any) -> Any:
        return SimpleNamespace(success=True)

    async def _fake_save_context_session(context: Any, account_info: Any) -> bool:
        saved_sessions.append(context)
        return True

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        _fake_open_persistent_runtime_bundle,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.prime_runtime_page_for_login_gate",
        _fake_prime,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.python_component_adapter.create_adapter",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_dir,
    )
    monkeypatch.setattr(tester, "_run_login_with_verification_support", _fake_login)
    monkeypatch.setattr(tester, "_save_context_session", _fake_save_context_session)

    # 账号锁用假实现: 既验证「回退阶段也要走同一把跨进程锁」, 又不会把进程内锁
    # 单例按住不放(会污染同会话里其它用例)。
    lock_calls: List[Dict[str, Any]] = []

    async def _fake_open_lock(**kwargs: Any) -> None:
        lock_calls.append(kwargs)
        return None

    monkeypatch.setattr(tester, "_open_profile_session_lock", _fake_open_lock)

    old_context = _FakeClosable()

    ok, new_context, new_page = await tester._run_headful_login_fallback(
        browser_type=object(),
        old_context=old_context,
        account_info=account_info,
        login_class=object(),
        component_name="tiktok/login",
        result=ComponentTestResult(
            component_name="login",
            platform="tiktok",
            status=TestStatus.PENDING,
        ),
    )

    assert ok is True
    assert new_context == "context-2"
    assert new_page == "page-2"

    # 1) 两次打开都在**同一个 profile 目录**上(主账号 ID 命名)
    assert len(opened) == 2
    for call in opened:
        assert call["profile_path_override"] == str(profile_dir)
        assert call["session_owner_id"] == "main-1"
        assert call["platform"] == "tiktok"

    # 2) 有头那一次必须是 headed; 重开沿用测试器的 headless 设置
    assert opened[0]["launch_kwargs"]["headless"] is False
    assert opened[1]["launch_kwargs"]["headless"] is True

    # 3) 旧 context 必须先关掉(释放 Chromium ProcessSingleton)
    assert old_context.closed == 1

    # 4) 不再写会话文件
    assert saved_sessions == []

    # 5) 重开后必须 prime 页面(否则登录闸门在 about:blank 上判定不了登录态)
    assert len(primed) == 1
    assert primed[0]["page"] == "page-2"
    assert primed[0]["platform"] == "tiktok"
    assert primed[0]["account"] is account_info

    # 6) 回退阶段会再次打开同一个 profile 目录 -> 必须走同一把跨进程账号锁
    assert lock_calls == [
        {"persistent_context_mode": "reused", "session_owner_id": "main-1"}
    ]


def test_headful_fallback_source_has_no_session_file_relay():
    """旧实现是「写会话文件 -> 读会话文件重建主 context」, 必须彻底消失。"""
    import ast

    source = TEST_COMPONENT_PATH.read_text(encoding="utf-8", errors="replace")

    assert "_recreate_context_with_saved_session" not in source

    # 回退函数体内不得再出现会话文件读写
    tree = ast.parse(source)
    fallback = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_run_headful_login_fallback"
    )
    used_names = {
        node.id for node in ast.walk(fallback) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(fallback) if isinstance(node, ast.Attribute)
    }
    assert "load_or_bootstrap_runtime_storage_state" not in used_names
    assert "persist_runtime_session_state" not in used_names
    assert "_save_context_session" not in used_names
