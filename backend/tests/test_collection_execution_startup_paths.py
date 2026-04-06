from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_run_config_tasks_starts_background_execution(monkeypatch):
    from backend.routers import collection_tasks as module

    fake_task = SimpleNamespace(
        id=1,
        task_id="task-config-1",
        platform="shopee",
        account="shop-sg-1",
        status="pending",
        progress=0,
        current_step=None,
        files_collected=0,
        trigger_type="config",
        config_id=123,
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range={"start": "2026-04-06", "end": "2026-04-06"},
        total_domains=1,
        completed_domains=[],
        failed_domains=[],
        current_domain=None,
        debug_mode=False,
        error_message=None,
        duration_seconds=None,
        created_at=None,
        updated_at=None,
        started_at=None,
        completed_at=None,
        verification_type=None,
        verification_screenshot=None,
        time_selection=None,
    )
    create_tasks = AsyncMock(return_value=[fake_task])
    monkeypatch.setattr(
        "backend.services.collection_config_execution.create_tasks_for_config",
        create_tasks,
    )

    app = SimpleNamespace(state=SimpleNamespace())
    result = await module.run_config_tasks(
        config_id=123,
        fastapi_request=SimpleNamespace(app=app),
        db=object(),
    )

    create_tasks.assert_awaited_once_with(
        object(),
        config_id=123,
        trigger_type="config",
        app=app,
        start_background=True,
        resolve_runtime=True,
    )
    assert result[0]["task_id"] == "task-config-1"


class _AsyncSessionManager:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_execute_scheduled_collection_config_starts_background_execution(monkeypatch):
    from backend.services import collection_scheduler as module

    fake_config = SimpleNamespace(
        id=27,
        is_active=True,
        schedule_enabled=True,
        schedule_cron="0 6 * * *",
    )
    fake_result = SimpleNamespace(scalar_one_or_none=lambda: fake_config)
    fake_session = SimpleNamespace(execute=AsyncMock(return_value=fake_result))
    create_tasks = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal",
        lambda: _AsyncSessionManager(fake_session),
    )
    monkeypatch.setattr(
        "backend.services.collection_config_execution.create_tasks_for_config",
        create_tasks,
    )

    await module.execute_scheduled_collection_config(27)

    create_tasks.assert_awaited_once_with(
        fake_session,
        config_id=27,
        trigger_type="scheduled",
        start_background=True,
        resolve_runtime=True,
    )
