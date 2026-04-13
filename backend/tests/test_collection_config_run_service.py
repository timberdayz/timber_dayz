import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CollectionConfig, CollectionConfigRun, CollectionTask


@pytest_asyncio.fixture
async def config_run_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CollectionConfig.__table__.create)
        await conn.run_sync(CollectionConfigRun.__table__.create)
        await conn.run_sync(CollectionTask.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def config_run_session_factory(config_run_engine):
    return async_sessionmaker(config_run_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def config_run_session(config_run_session_factory):
    async with config_run_session_factory() as session:
        yield session


async def _seed_config(session):
    config = CollectionConfig(
        name="queue-config-v1",
        platform="shopee",
        main_account_id="main-shopee",
        account_ids=["shop-sg-1"],
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range_type="yesterday",
        schedule_enabled=True,
        schedule_cron="0 6 * * *",
        retry_count=3,
        execution_mode="headless",
        is_active=True,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


@pytest.mark.asyncio
async def test_enqueue_config_run_creates_queued_run(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)

    run, created = await service.enqueue_config_run(config, trigger_type="scheduled")

    assert created is True
    assert run.config_id == config.id
    assert run.status == "queued"
    assert run.trigger_type == "scheduled"


@pytest.mark.asyncio
async def test_enqueue_config_run_reuses_existing_active_run(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)

    first_run, created = await service.enqueue_config_run(config, trigger_type="scheduled")
    second_run, second_created = await service.enqueue_config_run(config, trigger_type="scheduled")

    assert created is True
    assert second_created is False
    assert second_run.id == first_run.id


@pytest.mark.asyncio
async def test_claim_next_queued_run_marks_oldest_run_running(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)

    first_run, _ = await service.enqueue_config_run(config, trigger_type="scheduled")
    await service.mark_run_failed(first_run.id, error_message="done")
    second_run, _ = await service.enqueue_config_run(config, trigger_type="manual")

    claimed = await service.claim_next_queued_run()

    assert claimed is not None
    assert claimed.id == second_run.id
    assert claimed.status == "running"
    assert claimed.started_at is not None


@pytest.mark.asyncio
async def test_finalize_run_marks_completed_when_all_tasks_complete(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    run, _ = await service.enqueue_config_run(config, trigger_type="scheduled")
    claimed = await service.claim_next_queued_run()

    config_run_session.add(
        CollectionTask(
            task_id="task-1",
            config_id=config.id,
            config_run_id=claimed.id,
            platform=config.platform,
            account="shop-sg-1",
            status="completed",
            progress=100,
            trigger_type="scheduled",
            data_domains=["orders"],
            sub_domains=None,
            granularity="daily",
            date_range={"start_date": "2026-04-09", "end_date": "2026-04-09"},
            total_domains=1,
            completed_domains=["orders"],
            failed_domains=[],
            current_domain=None,
            debug_mode=False,
        )
    )
    await config_run_session.commit()

    finalized = await service.finalize_run_from_tasks(claimed.id)

    assert finalized.status == "completed"
    assert finalized.completed_at is not None


@pytest.mark.asyncio
async def test_finalize_run_marks_partial_success_when_tasks_mixed(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    run, _ = await service.enqueue_config_run(config, trigger_type="scheduled")
    claimed = await service.claim_next_queued_run()

    config_run_session.add_all(
        [
            CollectionTask(
                task_id="task-1",
                config_id=config.id,
                config_run_id=claimed.id,
                platform=config.platform,
                account="shop-sg-1",
                status="completed",
                progress=100,
                trigger_type="scheduled",
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range={"start_date": "2026-04-09", "end_date": "2026-04-09"},
                total_domains=1,
                completed_domains=["orders"],
                failed_domains=[],
                current_domain=None,
                debug_mode=False,
            ),
            CollectionTask(
                task_id="task-2",
                config_id=config.id,
                config_run_id=claimed.id,
                platform=config.platform,
                account="shop-my-1",
                status="failed",
                progress=0,
                trigger_type="scheduled",
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range={"start_date": "2026-04-09", "end_date": "2026-04-09"},
                total_domains=1,
                completed_domains=[],
                failed_domains=[{"domain": "orders", "error": "boom"}],
                current_domain=None,
                debug_mode=False,
            ),
        ]
    )
    await config_run_session.commit()

    finalized = await service.finalize_run_from_tasks(claimed.id)

    assert finalized.status == "partial_success"


@pytest.mark.asyncio
async def test_get_running_run_returns_only_running_instance(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    queued_run, _ = await service.enqueue_config_run(config, trigger_type="scheduled")
    await service.claim_next_queued_run()

    running = await service.get_running_run()
    assert running is not None
    assert running.id == queued_run.id

    rows = (
        await config_run_session.execute(select(CollectionConfigRun))
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_mark_running_runs_failed_marks_only_active_running_runs(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    running_run, _ = await service.enqueue_config_run(config, trigger_type="scheduled")
    await service.claim_next_queued_run()
    config_run_session.add(
        CollectionTask(
            task_id="stale-verification-task",
            config_id=config.id,
            config_run_id=running_run.id,
            platform=config.platform,
            account="shop-sg-1",
            status="verification_submitted",
            progress=50,
            trigger_type="scheduled",
            data_domains=["orders"],
            sub_domains=None,
            granularity="daily",
            date_range={"start_date": "2026-04-09", "end_date": "2026-04-09"},
            total_domains=1,
            completed_domains=[],
            failed_domains=[],
            current_domain="orders",
            debug_mode=False,
        )
    )
    queued_run = CollectionConfigRun(
        run_id="queued-run",
        config_id=config.id,
        platform=config.platform,
        main_account_id=config.main_account_id,
        trigger_type="scheduled",
        status="queued",
    )
    config_run_session.add(queued_run)

    config_run_session.add(
        CollectionConfigRun(
            run_id="completed-run",
            config_id=config.id,
            platform=config.platform,
            main_account_id=config.main_account_id,
            trigger_type="scheduled",
            status="completed",
        )
    )
    await config_run_session.commit()
    await config_run_session.refresh(queued_run)

    updated_runs = await service.mark_running_runs_failed(
        error_message="service restarted before config run completed"
    )

    assert [run.id for run in updated_runs] == [running_run.id]
    assert updated_runs[0].status == "failed"
    assert updated_runs[0].completed_at is not None

    refreshed_queued = await service._get_run(queued_run.id)
    assert refreshed_queued.status == "queued"

    recovered_task = (
        await config_run_session.execute(
            select(CollectionTask).where(CollectionTask.task_id == "stale-verification-task")
        )
    ).scalar_one()
    assert recovered_task.status == "failed"
    assert recovered_task.completed_at is not None
    assert recovered_task.error_message == "service restarted before config run completed"


@pytest.mark.asyncio
async def test_cancel_run_by_run_id_marks_queued_run_cancelled(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    queued_run, _ = await service.enqueue_config_run(config, trigger_type="manual")

    cancelled = await service.cancel_run_by_run_id(queued_run.run_id)

    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_run_by_run_id_rejects_non_queued_run(config_run_session):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    config = await _seed_config(config_run_session)
    service = CollectionConfigRunService(config_run_session)
    queued_run, _ = await service.enqueue_config_run(config, trigger_type="manual")
    await service.claim_next_queued_run()

    with pytest.raises(ValueError, match="only queued config runs can be cancelled"):
        await service.cancel_run_by_run_id(queued_run.run_id)
