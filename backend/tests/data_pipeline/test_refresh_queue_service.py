from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import RefreshQueueTask


@pytest_asyncio.fixture
async def refresh_queue_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(RefreshQueueTask.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_refresh_inserts_pending_row(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="data_ingested_refresh",
        targets=["semantic.fact_services_atomic"],
        context={"file_id": 1},
    )

    assert task.status == "pending"
    assert task.pipeline_name == "data_ingested_refresh"
    assert task.targets_json == ["semantic.fact_services_atomic"]


@pytest.mark.asyncio
async def test_enqueue_refresh_coalesces_same_pending_targets(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    first = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="data_ingested_refresh",
        targets=["semantic.fact_services_atomic"],
        context={"related_file_ids": [1]},
    )
    second = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="data_ingested_refresh",
        targets=["semantic.fact_services_atomic"],
        context={"related_file_ids": [2]},
    )

    rows = (
        await refresh_queue_session.execute(select(RefreshQueueTask).order_by(RefreshQueueTask.id))
    ).scalars().all()

    assert len(rows) == 1
    assert first.id == second.id
    assert rows[0].context_json["related_file_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_claim_next_refresh_task_marks_oldest_pending_running(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    older = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-a",
        targets=["semantic.a"],
        context={"file_id": 1},
    )
    newer = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-b",
        targets=["semantic.b"],
        context={"file_id": 2},
    )

    claimed = await service.claim_next_refresh_task()

    assert claimed.id == older.id
    assert claimed.status == "running"

    refreshed_newer = await refresh_queue_session.get(RefreshQueueTask, newer.id)
    assert refreshed_newer.status == "pending"


@pytest.mark.asyncio
async def test_mark_completed_and_failed_update_terminal_state(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    completed = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-complete",
        targets=["semantic.complete"],
        context={},
    )
    failed = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-fail",
        targets=["semantic.fail"],
        context={},
    )

    await service.mark_completed(completed.id)
    await service.mark_failed(failed.id, "boom")

    completed_row = await refresh_queue_session.get(RefreshQueueTask, completed.id)
    failed_row = await refresh_queue_session.get(RefreshQueueTask, failed.id)

    assert completed_row.status == "completed"
    assert completed_row.finished_at is not None
    assert failed_row.status == "failed"
    assert failed_row.last_error == "boom"
    assert failed_row.finished_at is not None


@pytest.mark.asyncio
async def test_claim_next_refresh_task_skips_when_another_task_is_running(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    running_task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-running",
        targets=["semantic.running"],
        context={"file_id": 10},
    )
    pending_task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-pending",
        targets=["semantic.pending"],
        context={"file_id": 11},
    )

    running_task.status = "running"
    await refresh_queue_session.commit()

    claimed = await service.claim_next_refresh_task()

    assert claimed is None

    refreshed_pending = await refresh_queue_session.get(RefreshQueueTask, pending_task.id)
    assert refreshed_pending.status == "pending"


@pytest.mark.asyncio
async def test_recover_stale_running_tasks_marks_timed_out_rows_failed(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-stale",
        targets=["semantic.stale"],
        context={"file_id": 20},
    )
    task.status = "running"
    task.started_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    await refresh_queue_session.commit()

    recovered = await service.recover_stale_running_tasks(timeout_seconds=60)

    assert recovered == 1
    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "failed"
    assert "timed out" in (refreshed.last_error or "")
