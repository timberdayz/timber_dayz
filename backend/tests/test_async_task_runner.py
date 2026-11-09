"""契约测试：统一异步出口(backend/utils/async_task_runner.py)。

为什么必须有这个出口（SSOT）
---------------------------
2026-11-09 生产只读调查：生产库 80 个连接槽位**全部打满**且只增不减，
最早一条连接存活 8 小时 27 分钟，最后一条 SQL 是 ``COMMIT;``（事务已提交，
连接本身没关）。

根因是「异步任务的收尾」没有唯一做法：历史实现用
``async_engine.sync_engine.dispose(close=False)``，它只把连接池标记作废，
**不关闭底层 TCP 连接**；而连接绑定在已结束的事件循环上，之后想补关都关不掉。

本模块把收尾收敛成唯一出口：``run_async_task`` 在**循环仍存活时**真正关闭
连接池（``await async_engine.dispose()``，等价于 close=True）。
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from backend.utils.async_task_runner import run_async_task


def test_returns_task_result():
    async def _task():
        await asyncio.sleep(0)
        return {"ok": True}

    assert run_async_task(_task) == {"ok": True}


def test_accepts_awaitable_directly():
    async def _task():
        return 42

    assert run_async_task(_task()) == 42


def test_closes_engine_after_task(monkeypatch):
    """任务结束后必须真正关闭连接池（close=True 语义）。"""
    from backend.models import database as database_module

    closed = {"count": 0}

    async def _fake_dispose():
        closed["count"] += 1

    monkeypatch.setattr(
        database_module, "dispose_async_engine", _fake_dispose, raising=False
    )

    async def _task():
        return "done"

    assert run_async_task(_task) == "done"
    assert closed["count"] == 1


def test_closes_engine_even_when_task_raises(monkeypatch):
    """任务失败也必须收尾，否则异常路径上会留下更多泄漏连接。"""
    from backend.models import database as database_module

    closed = {"count": 0}

    async def _fake_dispose():
        closed["count"] += 1

    monkeypatch.setattr(
        database_module, "dispose_async_engine", _fake_dispose, raising=False
    )

    async def _task():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_async_task(_task)

    assert closed["count"] == 1


def test_dispose_failure_is_surfaced(monkeypatch):
    """收尾失败不能被吞掉——连接可能残留，必须显形。"""
    from backend.models import database as database_module

    async def _fake_dispose():
        raise RuntimeError("dispose failed")

    monkeypatch.setattr(
        database_module, "dispose_async_engine", _fake_dispose, raising=False
    )

    async def _task():
        return "done"

    with pytest.raises(RuntimeError, match="dispose failed"):
        run_async_task(_task)


def test_dispose_failure_does_not_mask_task_error(monkeypatch):
    """任务本身失败时，收尾异常不得覆盖原始异常（否则根因会被掩盖）。"""
    from backend.models import database as database_module

    async def _fake_dispose():
        raise RuntimeError("dispose failed")

    monkeypatch.setattr(
        database_module, "dispose_async_engine", _fake_dispose, raising=False
    )

    async def _task():
        raise ValueError("original failure")

    with pytest.raises(ValueError, match="original failure"):
        run_async_task(_task)


def test_rejects_invalid_task_type():
    with pytest.raises(TypeError):
        run_async_task("not-a-coroutine")


def test_skip_dispose_when_database_module_never_loaded(monkeypatch):
    """纯 CLI 工具没有加载数据库模块时，不应该为了收尾反向导入数据库。"""
    monkeypatch.delitem(sys.modules, "backend.models.database", raising=False)

    async def _task():
        return "ok"

    assert run_async_task(_task) == "ok"
