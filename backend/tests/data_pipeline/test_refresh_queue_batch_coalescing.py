"""批次 H 守护测试:「入库批量刷新」(刷新队列的合并语义)。

背景
----
一次入库会刷 25 个物化视图, 单次实测 170 秒以上。
以前刷新队列只合并「pending」的任务 ⇒ 一条刷新**正在跑**的时候新到的文件
会另起一条新任务 ⇒ 一轮入库(几十个积压文件)会刷出**好几轮**完整刷新。

现在:
* 新事件被**正在跑**的那条吸收(上下文打 ``rerun_requested`` 标记);
* 它跑完后发现标记 ⇒ 重新排回 pending ⇒ 再刷一轮收口。

⇒ 一轮入库至多「跑中的那一轮 + 收口的那一轮」, 而不是「每个文件一轮」。

口径来源: ``docs/reports/2026-11-07-shop-identity-and-template-sync-incident.md``
问题 5。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import RefreshQueueTask


@pytest_asyncio.fixture
async def batch_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(RefreshQueueTask.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


_TARGETS = ["semantic.fact_orders_monthly_atomic_mv", "mart.platform_day_kpi"]


async def _enqueue(service, file_id: int):
    return await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="data_ingested_refresh",
        targets=list(_TARGETS),
        context={"file_id": file_id, "related_file_ids": [file_id]},
    )


@pytest.mark.asyncio
async def test_running_task_absorbs_events_that_arrive_while_it_runs(batch_session):
    """**正在跑**的那条刷新必须吸收后来到的事件(而不是另起一条)。"""
    from backend.services.data_pipeline.refresh_queue_service import (
        RERUN_REQUESTED_FLAG,
        RefreshQueueService,
    )

    service = RefreshQueueService(batch_session)
    first = await _enqueue(service, 1)
    claimed = await service.claim_next_refresh_task()
    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.status == "running"

    later = await _enqueue(service, 2)

    assert later.id == first.id, "后来到的事件必须并入正在跑的那条"
    assert (later.context_json or {}).get(RERUN_REQUESTED_FLAG) is True
    assert (later.context_json or {}).get("related_file_ids") == [1, 2]


@pytest.mark.asyncio
async def test_completed_task_is_requeued_when_new_data_arrived_during_the_run(
    batch_session,
):
    """跑完发现有新数据 ⇒ 不落 completed, 而是重新排回 pending 收口。"""
    from backend.services.data_pipeline.refresh_queue_service import (
        RERUN_REQUESTED_FLAG,
        RefreshQueueService,
    )

    service = RefreshQueueService(batch_session)
    task = await _enqueue(service, 1)
    claimed = await service.claim_next_refresh_task()
    assert claimed is not None

    # 跑的过程中又来了两个文件
    await _enqueue(service, 2)
    await _enqueue(service, 3)

    result = await service.mark_completed(task.id)
    assert result.status == "pending", "必须重新排回 pending, 而不是落 completed"
    assert (result.context_json or {}).get(RERUN_REQUESTED_FLAG) is None

    # 收口轮跑完 ⇒ 才算完成
    final = await service.mark_completed(task.id)
    assert final.status == "completed"


@pytest.mark.asyncio
async def test_completed_task_is_marked_completed_when_nothing_arrived(batch_session):
    """没有新数据 ⇒ 与从前一致(直接 completed)。"""
    from backend.services.data_pipeline.refresh_queue_service import (
        RefreshQueueService,
    )

    service = RefreshQueueService(batch_session)
    task = await _enqueue(service, 1)
    await service.claim_next_refresh_task()

    result = await service.mark_completed(task.id)
    assert result.status == "completed"
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_one_ingest_wave_costs_two_refresh_runs_not_one_per_file(batch_session):
    """**吞吐口径**: 5 个文件入库 ⇒ 只跑 2 轮刷新(而不是 5 轮)。

    场景: 3 个文件先入库(合并成 1 条 pending)→ worker 领走开始跑 →
    跑的过程中又来 2 个文件 → 收口轮再刷一次 → 结束。
    """
    from backend.services.data_pipeline.refresh_queue_service import (
        RefreshQueueService,
    )

    service = RefreshQueueService(batch_session)

    for file_id in (1, 2, 3):
        await _enqueue(service, file_id)

    tasks = (
        await batch_session.execute(
            text("select id from core.refresh_queue_tasks order by id")
        )
    ).fetchall()
    assert len(tasks) == 1, "同一波入库必须合并成一条任务"

    first_run = await service.claim_next_refresh_task()
    assert first_run is not None

    # 跑的过程中又来两个
    for file_id in (4, 5):
        await _enqueue(service, file_id)

    tasks = (
        await batch_session.execute(
            text("select id from core.refresh_queue_tasks order by id")
        )
    ).fetchall()
    assert len(tasks) == 1, "跑的过程中来的文件也不该另起一条"

    await service.mark_completed(first_run.id)

    second_run = await service.claim_next_refresh_task()
    assert second_run is not None, "收口轮必须还能被领到"
    assert second_run.id == first_run.id
    await service.mark_completed(second_run.id)

    # 收口轮跑完 ⇒ 这一波彻底结束; 之后再来的文件是**新的一波** ⇒ 新任务
    await _enqueue(service, 6)
    third_run = await service.claim_next_refresh_task()
    assert third_run is not None
    assert third_run.id != first_run.id, "已经收口的一波不该被复活成同一条"


@pytest.mark.asyncio
async def test_different_targets_still_get_separate_tasks(batch_session):
    """合并只发生在「同目标」上 —— 不同目标仍是两条。"""
    from backend.services.data_pipeline.refresh_queue_service import (
        RefreshQueueService,
    )

    service = RefreshQueueService(batch_session)
    await _enqueue(service, 1)
    await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="data_ingested_refresh",
        targets=["semantic.fact_services_atomic"],
        context={"file_id": 2},
    )

    rows = (
        await batch_session.execute(
            text("select id from core.refresh_queue_tasks order by id")
        )
    ).fetchall()
    assert len(rows) == 2
