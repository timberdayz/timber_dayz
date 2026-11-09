"""异步引擎「按事件循环分发」契约测试。

2026-11-09 生产连接泄漏根治（第二版）的核心不变量：

* **每个事件循环有自己的引擎（和连接池）** —— asyncpg 的连接绑定在创建它的
  事件循环上；共用一个池 ⇒ 循环 A 建的连接被循环 B checkout 时 pre_ping 失败，
  连接被丢弃；又因为原循环已结束，close 同样失败 ⇒ TCP 连接滞留在数据库
  服务端白占槽位（生产实测 80/80 打满、只增不减、最早一条存活 8 小时 27 分）。

* **连接池不能丢** —— NullPool 也能消除跨循环复用，但生产容器实测
  NullPool 14.21 ms/次、池化 1.79 ms/次（8 倍差距）。按循环分发既根治泄漏，
  又保住连接复用。

* **每个引擎都必须挂上 connect 监听器** —— search_path 与 statement_timeout
  是靠监听器设的；引擎改成按循环创建后，少挂一个就会让那条连接「裸奔」。

* **自建会话必须自己关闭** —— 漏关一条会话就是漏一条数据库连接。
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text


# --------------------------------------------------------------------------
# 1) 引擎按事件循环分发
# --------------------------------------------------------------------------


def test_same_loop_reuses_the_same_engine():
    """同一个事件循环里必须复用同一个引擎（连接池才有意义）。"""

    async def _probe():
        from backend.models.database import get_async_engine

        return get_async_engine(), get_async_engine()

    first, second = asyncio.run(_probe())

    assert first is second, "同一事件循环里应该复用同一个引擎（否则连接池失效）"


def test_different_loops_get_different_engines():
    """不同事件循环必须拿到**不同**的引擎 —— 这就是根治跨循环复用的关键。"""

    async def _probe():
        from backend.models.database import get_async_engine

        return get_async_engine()

    first = asyncio.run(_probe())
    second = asyncio.run(_probe())

    assert first is not second, "两个事件循环共用了同一个引擎 —— 连接会跨循环复用"


def test_engine_keeps_a_real_connection_pool():
    """按循环分发之后，池化能力必须还在（否则接口延迟会退化 8 倍）。"""
    from backend.models.database import get_async_engine

    async def _probe():
        engine = get_async_engine()
        return engine.pool

    pool = asyncio.run(_probe())

    for method_name in ("size", "checkedout", "overflow", "status"):
        assert hasattr(pool, method_name), (
            f"引擎应当仍是池化的（缺少 {method_name}()）—— "
            "生产实测 NullPool 比池化慢 8 倍"
        )


def test_dispose_removes_engine_from_registry():
    """收尾必须把引擎从注册表摘掉 —— 短命循环才不会在注册表里越堆越多。"""
    from backend.models.database import _ASYNC_ENGINE_REGISTRY, get_async_engine

    async def _probe():
        before = get_async_engine()
        _ASYNC_ENGINE_REGISTRY.pop_current_loop_engine()
        after = get_async_engine()
        return before, after

    before, after = asyncio.run(_probe())

    assert before is not after, "dispose 之后应当重新建一个引擎，而不是复用旧的"


def test_every_engine_has_the_search_path_listener():
    """每个按循环创建的引擎都必须挂上 connect 监听器。

    [*] 少了监听器 ⇒ 那条连接既没有 search_path（找不到 schema 里的表），
    也没有 statement_timeout（长事务会拖垮数据库）。
    """
    from backend.models.database import get_async_engine

    async def _probe():
        engine = get_async_engine()
        async with engine.connect() as conn:
            search_path = await conn.execute(text("SHOW search_path"))
            timeout = await conn.execute(text("SHOW statement_timeout"))
        return str(search_path.scalar()), str(timeout.scalar())

    search_path, timeout = asyncio.run(_probe())

    assert "core" in search_path, f"search_path 没设对：{search_path}"
    assert timeout not in ("0", ""), f"statement_timeout 没设对：{timeout}"


# --------------------------------------------------------------------------
# 2) 审计服务自建会话必须关闭
# --------------------------------------------------------------------------


class _FakeScalarResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    """最小可用的 AsyncSession 替身。"""

    def __init__(self) -> None:
        self.closed = False
        self.committed = False
        self.rolled_back = False

    async def execute(self, *args, **kwargs):
        return _FakeScalarResult()

    def add(self, obj) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


def _install_fake_sessions(monkeypatch) -> list[_FakeSession]:
    from backend.models import database as database_module

    created: list[_FakeSession] = []

    def _factory():
        session = _FakeSession()
        created.append(session)
        return session

    monkeypatch.setattr(database_module, "AsyncSessionLocal", _factory)
    return created


@pytest.mark.asyncio
async def test_audit_service_closes_self_created_session(monkeypatch):
    """db=None 时自建的会话必须被关闭（否则每次审计都漏一条连接）。"""
    from backend.services.audit_service import AuditService

    created = _install_fake_sessions(monkeypatch)

    await AuditService().log_action(
        user_id=1,
        action="update",
        resource="shop",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert len(created) == 1
    assert created[0].closed is True, "自建的会话没有关闭 —— 会漏数据库连接"


@pytest.mark.asyncio
async def test_audit_service_closes_session_on_error(monkeypatch):
    """业务失败时也必须关闭自建的会话（finally 语义）。"""
    from backend.models import database as database_module
    from backend.services.audit_service import AuditService

    created: list[_FakeSession] = []

    class _BrokenSession(_FakeSession):
        async def commit(self) -> None:
            raise RuntimeError("提交失败")

    def _factory():
        session = _BrokenSession()
        created.append(session)
        return session

    monkeypatch.setattr(database_module, "AsyncSessionLocal", _factory)

    await AuditService().log_action(
        user_id=1,
        action="update",
        resource="shop",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert len(created) == 1
    assert created[0].closed is True, "异常路径下自建的会话没有关闭"


@pytest.mark.asyncio
async def test_audit_service_does_not_close_caller_session(monkeypatch):
    """调用方传进来的会话不归审计服务关 —— 不能越权关闭别人的会话。"""
    from backend.services.audit_service import AuditService

    created = _install_fake_sessions(monkeypatch)
    caller_session = _FakeSession()

    await AuditService().log_action(
        user_id=1,
        action="update",
        resource="shop",
        ip_address="127.0.0.1",
        user_agent="pytest",
        db=caller_session,
    )

    assert created == [], "传了 db 就不应该再自建会话"
    assert caller_session.closed is False, "审计服务不应关闭调用方的会话"
    assert caller_session.committed is True


@pytest.mark.asyncio
async def test_sync_and_change_audit_also_close_self_created_session(monkeypatch):
    """另外两个审计入口同样必须关闭自建的会话。"""
    from backend.services.audit_service import AuditService

    created = _install_fake_sessions(monkeypatch)
    service = AuditService()

    await service.log_sync_operation(
        user_id=None, file_id=1, task_id="t1", operation="sync_start", details={}
    )
    await service.log_data_change(
        user_id=None,
        resource_type="order",
        resource_id="1",
        action="update",
        before=None,
        after=None,
    )

    assert len(created) == 2
    assert all(session.closed for session in created), "有审计入口没有关闭自建会话"
