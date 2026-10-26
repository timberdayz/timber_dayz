"""数据库会话收尾的行为约定。

`get_async_db` 的收尾**不能**把一次本来正常的请求打成 500。

背景（2026-10-26 线上事故）
--------------------------
收尾是 ``await session.commit()`` 紧接 ``await session.close()``。
``close()`` 会撞上「还在进行中的 commit」→
``IllegalStateChangeError: Method 'close()' can't be called here;
method 'commit()' is already in progress``。

触发场景：客户端超时断开（请求被取消，commit 被取消但还没结束）、
或有协程并发用了这个会话。

那次事故让 ``GET /api/data-sync/governance/stats`` 连报 4 次 500，
页面上的「数据治理概览」整片变成 ``--``。
收尾失败只说明「连接可能没干净归还」，不该改写本次请求的结果。
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeSession:
    """最小可用的 AsyncSession 替身。"""

    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.close_error = close_error
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


@pytest.mark.asyncio
async def test_get_async_db_commits_and_closes_on_success(monkeypatch):
    """正常路径：提交 + 关闭都做。"""
    from backend.models import database as database_module

    session = _FakeSession()
    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: session)

    generator = database_module.get_async_db()
    await generator.__anext__()
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()

    assert session.committed is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_get_async_db_swallows_close_failure(monkeypatch):
    """**关会话失败不能把请求打成 500** —— 收尾只记录，不上抛。"""
    from backend.models import database as database_module

    session = _FakeSession(
        close_error=RuntimeError(
            "Method 'close()' can't be called here; "
            "method 'commit()' is already in progress"
        )
    )
    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: session)

    generator = database_module.get_async_db()
    await generator.__anext__()
    # 关键：收尾不抛异常 → 请求不会被打成 500
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()

    assert session.committed is True


@pytest.mark.asyncio
async def test_get_async_db_rolls_back_and_reraises_on_error(monkeypatch):
    """业务异常仍然要回滚并原样抛出（不能被收尾逻辑吞掉）。"""
    from backend.models import database as database_module

    session = _FakeSession()
    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: session)

    generator = database_module.get_async_db()
    await generator.__anext__()
    with pytest.raises(ValueError, match="业务失败"):
        await generator.athrow(ValueError("业务失败"))

    assert session.rolled_back is True
