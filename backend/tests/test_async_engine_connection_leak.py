"""泄漏回归测试：反复执行异步任务后，数据库连接数不得增长。

这是 2026-11-09 生产连接泄漏的**直接证伪测试**。

生产实况（只读调查）：80 个连接槽位全部打满且只增不减（≈0.75 条/分钟），
最早一条连接存活 8 小时 27 分钟，最后一条 SQL 是 ``COMMIT;``——事务已提交，
连接本身没关。

根因（本地已复现）：asyncpg 的连接绑定在**创建它的事件循环**上，而同一个
全局 async 引擎被三个不同的循环共用（FastAPI 主循环 / 后台线程自建循环 /
celery 每个 task 新建循环）。循环 A 建立的连接被循环 B checkout 时 pre_ping
必然失败，连接被丢弃；但因为原循环已结束，**close 同样失败** ⇒ TCP 连接
滞留在数据库服务端白占槽位。旧代码里的 ``dispose(close=False)`` 只是把池
「软丢弃」，既不关连接，也堵不住这个跨循环复用。

修复方式：async 引擎**按事件循环分发**——每个循环有自己的连接池，
连接永不跨循环复用；短命循环（celery task / 后台线程）在任务结束时
由统一出口 ``run_async_task`` 在**循环存活期间**真正关闭。

本测试的判定标准很朴素：**跑 N 轮任务，连接数不许涨。**
旧实现下这里必然失败；按事件循环分发之后必然通过。

配套的 ``test_leak_detector_can_see_the_old_behaviour`` 会把旧实现原样搬进
独立子进程跑一遍，确认这个探测器**确实有牙齿**。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.utils.async_task_runner import run_async_task

ROOT = Path(__file__).resolve().parents[2]

#: 允许的抖动（其它连接可能同时建立/断开）
_TOLERANCE = 1

#: 任务轮数：足以让「每轮漏一条」的旧实现明显暴露
_ROUNDS = 8


def _database_url() -> str:
    """取当前测试实际使用的数据库地址（护栏下指向一次性隔离库）。"""
    from backend.models.database import DATABASE_URL

    return DATABASE_URL


def _count_connections() -> int:
    """统计当前数据库上的客户端连接数（不含本查询自身）。"""

    async def _count() -> int:
        # [*] 必须用「当前事件循环的引擎」—— 引擎按事件循环分发，
        # 用全局 async_engine 会把连接算到别的循环头上。
        from backend.models.database import get_async_engine

        async with get_async_engine().connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() "
                    "AND backend_type = 'client backend'"
                )
            )
            return int(result.scalar() or 0)

    return run_async_task(_count)


def _work_coroutine():
    """跑一个真实用到数据库的异步任务（返回协程，不自带收尾）。"""

    async def _work() -> int:
        from backend.models.database import AsyncSessionLocal

        session = AsyncSessionLocal()
        try:
            result = await session.execute(text("SELECT 1"))
            return int(result.scalar() or 0)
        finally:
            await session.close()

    return _work()


def _use_a_connection() -> int:
    """通过统一出口跑一次数据库任务（正常路径）。"""
    return run_async_task(_work_coroutine)


def _db_available() -> bool:
    try:
        _count_connections()
    except Exception:  # noqa: BLE001 - 基础设施不可用时明确跳过，而不是假装通过
        return False
    return True


@pytest.mark.skipif(
    not _db_available(), reason="测试数据库不可用（隔离库未启动），跳过连接泄漏回归"
)
def test_repeated_async_tasks_do_not_leak_connections():
    """连续跑多轮异步任务后，连接数不得增长。"""
    before = _count_connections()

    for _ in range(_ROUNDS):
        assert _use_a_connection() == 1

    after = _count_connections()

    assert after <= before + _TOLERANCE, (
        f"检测到连接泄漏：{_ROUNDS} 轮任务后连接数从 {before} 涨到 {after}。"
        "旧实现（dispose(close=False)）会留下关不掉的连接。"
    )


@pytest.mark.skipif(
    not _db_available(), reason="测试数据库不可用（隔离库未启动），跳过连接泄漏回归"
)
def test_leak_detector_can_see_the_old_behaviour():
    """证伪能力自检：模拟旧实现时，本探测器必须能看见问题。

    如果连旧实现都测不出问题，说明这个回归测试没有牙齿，
    也就无法为「修复有效」提供证据。

    旧实现会同时制造两种可观测故障：
    1. 连接关不掉，在数据库服务端持续占槽位；
    2. 连接绑定在已结束的循环上，后续再用到它就直接抛
       ``'NoneType' object has no attribute 'send'``。

    该场景会把进程内的连接池彻底污染，因此**放到独立子进程里跑**，
    避免影响同一测试会话里的其它用例。

    [*] 2026-11-09：旧实现的关键特征是「**全局 async 引擎 + 常驻连接池**
    被多个事件循环共用」。因此子进程**自建**一个 AsyncAdaptedQueuePool
    引擎来还原它 —— 不能直接用仓库现在的 async_engine（那已经是
    NullPool 了，拿它模拟旧实现就没有意义了）。
    """
    script = r"""
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from backend.models.database import DATABASE_URL, ASYNC_DATABASE_URL

# 用同步引擎统计连接数，避免统计动作本身参与异步连接池
counter = create_engine(DATABASE_URL)


def count():
    with counter.connect() as conn:
        r = conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() "
                "AND backend_type = 'client backend'"
            )
        )
        return int(r.scalar() or 0)


# 旧实现：全局 async 引擎用常驻连接池（跨事件循环复用同一批连接）
old_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
)


async def work():
    async with old_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


before = count()
for _ in range(4):
    # 历史实现：进入新循环前软丢弃连接池（不关闭连接）
    old_engine.sync_engine.dispose(close=False)
    # 历史实现：裸 asyncio.run，循环结束后连接再也关不掉
    asyncio.run(work())
after = count()
print("COUNT_BEFORE=%d" % before)
print("COUNT_AFTER=%d" % after)
"""
    env = dict(os.environ)
    env["DATABASE_URL"] = _database_url()

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    output = (result.stdout or "") + (result.stderr or "")
    growth_detected = False
    for line in output.splitlines():
        if line.startswith("COUNT_BEFORE="):
            before = int(line.split("=", 1)[1])
        if line.startswith("COUNT_AFTER="):
            after = int(line.split("=", 1)[1])
            growth_detected = after > before

    assert result.returncode != 0 or growth_detected, (
        "探测器失效：模拟旧实现（dispose(close=False) + 裸 asyncio.run）后"
        "既没有报错也没有连接增长，说明这个回归测试无法证伪。"
        f"\n子进程输出：\n{output[-2000:]}"
    )
