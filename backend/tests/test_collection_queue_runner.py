import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CollectionConfig, CollectionConfigRun, CollectionTask


@pytest_asyncio.fixture
async def queue_runner_engine():
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
def queue_runner_session_factory(queue_runner_engine):
    return async_sessionmaker(queue_runner_engine, expire_on_commit=False)


async def _seed_config(session_factory, *, name: str = "queue-config-v1"):
    async with session_factory() as session:
        config = CollectionConfig(
            name=name,
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
async def test_process_once_claims_one_queued_run(queue_runner_session_factory):
    from backend.services.collection_config_run_service import CollectionConfigRunService
    from backend.services.collection_queue_runner import CollectionQueueRunner

    config = await _seed_config(queue_runner_session_factory)
    async with queue_runner_session_factory() as session:
        run_service = CollectionConfigRunService(session)
        first_run, _ = await run_service.enqueue_config_run(config, trigger_type="scheduled")

    handled = []

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )

    async def _fake_process(run):
        handled.append(run.id)
        async with queue_runner_session_factory() as session:
            service = CollectionConfigRunService(session)
            await service.mark_run_failed(run.id, error_message="done")

    runner._process_run = _fake_process

    processed = await runner.process_once()

    assert processed is True
    assert handled == [first_run.id]


@pytest.mark.asyncio
async def test_process_once_does_not_claim_second_run_while_first_running(queue_runner_session_factory):
    from backend.services.collection_config_run_service import CollectionConfigRunService
    from backend.services.collection_queue_runner import CollectionQueueRunner

    config_a = await _seed_config(queue_runner_session_factory, name="queue-config-a")
    config_b = await _seed_config(queue_runner_session_factory, name="queue-config-b")
    async with queue_runner_session_factory() as session:
        run_service = CollectionConfigRunService(session)
        first_run, _ = await run_service.enqueue_config_run(config_a, trigger_type="scheduled")
        second_run, _ = await run_service.enqueue_config_run(config_b, trigger_type="scheduled")
        await run_service.claim_next_queued_run()

    handled = []
    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )

    async def _fake_process(run):
        handled.append(run.id)

    runner._process_run = _fake_process

    processed = await runner.process_once()

    assert processed is False
    assert handled == []
    assert second_run.id != first_run.id


@pytest.mark.asyncio
async def test_process_once_picks_next_run_after_previous_finishes(queue_runner_session_factory):
    from backend.services.collection_config_run_service import CollectionConfigRunService
    from backend.services.collection_queue_runner import CollectionQueueRunner

    config_a = await _seed_config(queue_runner_session_factory, name="queue-config-a")
    config_b = await _seed_config(queue_runner_session_factory, name="queue-config-b")
    async with queue_runner_session_factory() as session:
        run_service = CollectionConfigRunService(session)
        first_run, _ = await run_service.enqueue_config_run(config_a, trigger_type="scheduled")
        second_run, _ = await run_service.enqueue_config_run(config_b, trigger_type="scheduled")

    handled = []
    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )

    async def _fake_process(run):
        handled.append(run.id)
        async with queue_runner_session_factory() as session:
            service = CollectionConfigRunService(session)
            await service.mark_run_failed(run.id, error_message="done")

    runner._process_run = _fake_process

    first_processed = await runner.process_once()
    second_processed = await runner.process_once()

    assert first_processed is True
    assert second_processed is True
    assert handled == [first_run.id, second_run.id]


@pytest.mark.asyncio
async def test_runner_shutdown_stops_background_loop(queue_runner_session_factory):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    runner._process_once_impl = lambda: asyncio.sleep(0)

    await runner.start()
    assert runner._task is not None

    await runner.shutdown()

    assert runner._task is None


@pytest.mark.asyncio
async def test_process_run_executes_expanded_tasks_sequentially(queue_runner_session_factory):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    run = SimpleNamespace(id=11, config_id=21, trigger_type="scheduled")
    execution_order = []

    async def _fake_expand(_run):
        return [
            SimpleNamespace(
                task_id="task-1",
                platform="shopee",
                account="shop-sg-1",
                data_domains=["orders"],
                sub_domains=None,
                date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
                granularity="daily",
                debug_mode=False,
            ),
            SimpleNamespace(
                task_id="task-2",
                platform="shopee",
                account="shop-my-1",
                data_domains=["orders"],
                sub_domains=None,
                date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
                granularity="daily",
                debug_mode=False,
            ),
        ]

    async def _fake_execute(task, runtime_manifests=None):
        execution_order.append(task.task_id)

    finalized = []

    async def _fake_finalize(_run):
        finalized.append(_run.id)

    runner._expand_run_tasks = _fake_expand
    runner._execute_task = _fake_execute
    runner._finalize_run = _fake_finalize

    await runner._process_run(run)

    assert execution_order == ["task-1", "task-2"]
    assert finalized == [11]


@pytest.mark.asyncio
async def test_process_run_stops_before_next_task_when_run_is_cancelled(
    queue_runner_session_factory,
):
    from backend.services.collection_config_run_service import CollectionConfigRunService
    from backend.services.collection_queue_runner import CollectionQueueRunner

    config = await _seed_config(queue_runner_session_factory)
    async with queue_runner_session_factory() as session:
        service = CollectionConfigRunService(session)
        run, _ = await service.enqueue_config_run(config, trigger_type="manual")
        claimed = await service.claim_next_queued_run()

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    tasks = [
        SimpleNamespace(
            task_id="task-1",
            platform="shopee",
            account="shop-sg-1",
            data_domains=["orders"],
            sub_domains=None,
            date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
            granularity="daily",
            debug_mode=False,
        ),
        SimpleNamespace(
            task_id="task-2",
            platform="shopee",
            account="shop-sg-2",
            data_domains=["orders"],
            sub_domains=None,
            date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
            granularity="daily",
            debug_mode=False,
        ),
    ]
    execution_order = []

    async def _fake_expand(_run):
        return tasks

    async def _fake_execute(task, runtime_manifests=None):
        execution_order.append(task.task_id)
        async with queue_runner_session_factory() as session:
            service = CollectionConfigRunService(session)
            await service.cancel_run_by_run_id(run.run_id)

    runner._expand_run_tasks = _fake_expand
    runner._execute_task = _fake_execute

    await runner._process_run(claimed)

    assert execution_order == ["task-1"]


@pytest.mark.asyncio
async def test_process_run_passes_runtime_manifests_from_expansion_to_execute_task(
    queue_runner_session_factory,
):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    run = SimpleNamespace(id=12, config_id=22, trigger_type="scheduled")
    task = SimpleNamespace(
        task_id="task-1",
        platform="tiktok",
        account="shop-sg-1",
        data_domains=["products"],
        sub_domains=None,
        date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
        granularity="daily",
        debug_mode=False,
    )
    manifests = {
        "login": {"component_name": "tiktok/login"},
        "exports_by_domain": {"products": {"component_name": "tiktok/products_export"}},
    }

    async def _fake_expand(_run):
        return [(task, manifests)]

    captured: list[tuple[str, object | None]] = []

    async def _fake_execute(expanded_task, runtime_manifests=None):
        captured.append((expanded_task.task_id, runtime_manifests))

    finalized = []

    async def _fake_finalize(_run):
        finalized.append(_run.id)

    runner._expand_run_tasks = _fake_expand
    runner._execute_task = _fake_execute
    runner._finalize_run = _fake_finalize

    await runner._process_run(run)

    assert captured == [("task-1", manifests)]
    assert finalized == [12]


@pytest.mark.asyncio
async def test_process_run_raises_clear_error_when_no_tasks_are_expandable(
    queue_runner_session_factory,
):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    run = SimpleNamespace(id=13, config_id=23, trigger_type="scheduled")

    async def _fake_expand(_run):
        return []

    runner._expand_run_tasks = _fake_expand

    with pytest.raises(RuntimeError, match="produced no runnable tasks"):
        await runner._process_run(run)


@pytest.mark.asyncio
async def test_execute_task_forwards_runtime_manifests_to_background_executor(
    queue_runner_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    task = SimpleNamespace(
        task_id="task-1",
        platform="tiktok",
        account="shop-sg-1",
        data_domains=["products"],
        sub_domains=None,
        date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
        granularity="daily",
        debug_mode=False,
    )
    manifests = {
        "login": {"component_name": "tiktok/login"},
        "exports_by_domain": {"products": {"component_name": "tiktok/products_export"}},
    }

    captured = {}

    async def _fake_background(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "backend.routers.collection_tasks._execute_collection_task_background",
        _fake_background,
    )

    await runner._execute_task(task, runtime_manifests=manifests)

    assert captured["task_id"] == "task-1"
    assert captured["runtime_manifests"] == manifests


@pytest.mark.asyncio
async def test_execute_task_forwards_app_to_background_executor(
    queue_runner_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.services.collection_queue_runner import CollectionQueueRunner

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )
    runner.app = SimpleNamespace(state=SimpleNamespace(redis=object()))
    task = SimpleNamespace(
        task_id="task-2",
        platform="tiktok",
        account="shop-sg-2",
        data_domains=["products"],
        sub_domains=None,
        date_range={"start_date": "2026-04-10", "end_date": "2026-04-10"},
        granularity="daily",
        debug_mode=False,
    )

    captured = {}

    async def _fake_background(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "backend.routers.collection_tasks._execute_collection_task_background",
        _fake_background,
    )

    await runner._execute_task(task, runtime_manifests=None)

    assert captured["app"] is runner.app


@pytest.mark.asyncio
async def test_process_once_marks_run_failed_when_processing_raises(queue_runner_session_factory):
    from backend.services.collection_config_run_service import CollectionConfigRunService
    from backend.services.collection_queue_runner import CollectionQueueRunner

    config = await _seed_config(queue_runner_session_factory)
    async with queue_runner_session_factory() as session:
        run_service = CollectionConfigRunService(session)
        run, _ = await run_service.enqueue_config_run(config, trigger_type="scheduled")

    runner = CollectionQueueRunner(
        session_factory=queue_runner_session_factory,
        poll_interval_seconds=0.01,
    )

    async def _broken_process(_run):
        raise RuntimeError("boom")

    runner._process_run = _broken_process

    processed = await runner.process_once()

    assert processed is True
    async with queue_runner_session_factory() as session:
        run_service = CollectionConfigRunService(session)
        refreshed = await run_service._get_run(run.id)
        assert refreshed.status == "failed"
        assert "boom" in (refreshed.error_message or "")
