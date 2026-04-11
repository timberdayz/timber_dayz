from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_run_config_tasks_enqueues_config_run(monkeypatch):
    from backend.routers import collection_tasks as module

    fake_config = SimpleNamespace(
        id=123,
        platform="shopee",
        main_account_id="main-shopee",
        is_active=True,
    )
    fake_run = SimpleNamespace(
        id=1,
        run_id="run-config-1",
        config_id=123,
        platform="shopee",
        main_account_id="main-shopee",
        trigger_type="manual",
        status="queued",
        priority=5,
        scheduled_for=None,
        started_at=None,
        completed_at=None,
        error_message=None,
        created_at=None,
        updated_at=None,
    )
    fake_result = SimpleNamespace(scalar_one_or_none=lambda: fake_config)
    enqueue = AsyncMock(return_value=(fake_run, True))

    async def _fake_execute(stmt):
        return fake_result

    db = SimpleNamespace(execute=_fake_execute)
    monkeypatch.setattr(
        "backend.services.collection_config_run_service.CollectionConfigRunService",
        lambda db: SimpleNamespace(enqueue_config_run=enqueue),
    )

    result = await module.run_config_tasks(
        config_id=123,
        fastapi_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        db=db,
    )

    enqueue.assert_awaited_once_with(fake_config, trigger_type="manual")
    assert result["run_id"] == "run-config-1"
    assert result["status"] == "queued"


class _AsyncSessionManager:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_execute_scheduled_collection_config_enqueues_config_run(monkeypatch):
    from backend.services import collection_scheduler as module

    fake_config = SimpleNamespace(
        id=27,
        platform="shopee",
        main_account_id="main-shopee",
        is_active=True,
        schedule_enabled=True,
        schedule_cron="0 6 * * *",
    )
    fake_result = SimpleNamespace(scalar_one_or_none=lambda: fake_config)
    fake_session = SimpleNamespace(execute=AsyncMock(return_value=fake_result))
    fake_run = SimpleNamespace(id=3, run_id="run-27", status="queued")
    enqueue = AsyncMock(return_value=(fake_run, True))

    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal",
        lambda: _AsyncSessionManager(fake_session),
    )
    monkeypatch.setattr(
        "backend.services.collection_config_run_service.CollectionConfigRunService",
        lambda db: SimpleNamespace(enqueue_config_run=enqueue),
    )

    await module.execute_scheduled_collection_config(27)

    enqueue.assert_awaited_once_with(fake_config, trigger_type="scheduled")
