from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        task_id="task-1",
        platform="miaoshou",
        account="acc-1",
        status="running",
        progress=10,
        current_step="开始采集",
        files_collected=0,
        trigger_type="manual",
        data_domains=["orders"],
        sub_domains={"orders": ["tiktok"]},
        granularity="daily",
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        total_domains=1,
        completed_domains=[],
        failed_domains=[],
        current_domain="orders:tiktok",
        debug_mode=False,
        error_message=None,
        duration_seconds=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        verification_type=None,
        verification_screenshot=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_collection_step_status_callback_broadcasts_progress(monkeypatch):
    from backend.routers.collection_tasks import _collection_step_status_callback

    task = _make_task()
    result = MagicMock()
    result.scalar_one_or_none.return_value = task

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    send_progress = AsyncMock()
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _SessionManager())
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task", AsyncMock())
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task_log", AsyncMock())
    monkeypatch.setattr("backend.routers.collection_tasks.connection_manager.send_progress", send_progress)

    await _collection_step_status_callback(
        task_id=task.task_id,
        progress=55,
        message="正在导出订单",
        current_domain="orders:tiktok",
        details={"step_id": "export_orders"},
    )

    send_progress.assert_awaited_once_with(
        task.task_id,
        55,
        "正在导出订单",
        status="running",
    )


@pytest.mark.asyncio
async def test_execute_collection_task_background_broadcasts_complete_on_success(monkeypatch):
    from backend.routers.collection_tasks import _execute_collection_task_background

    task = _make_task(status="pending", progress=0, current_step=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = task

    db_session = MagicMock()
    db_session.execute = AsyncMock(return_value=result)
    db_session.commit = AsyncMock()

    class _DbSessionManager:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _ExecutorStub:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def execute(self, **kwargs):
            return SimpleNamespace(
                status="completed",
                files_collected=1,
                error_message=None,
                duration_seconds=12,
                completed_domains=["orders:tiktok"],
                failed_domains=[],
            )

    class _BrowserStub:
        close = AsyncMock()

    class _ChromiumStub:
        def __init__(self):
            self.launch = AsyncMock(return_value=_BrowserStub())

    class _PlaywrightStub:
        def __init__(self):
            self.chromium = _ChromiumStub()

    class _PlaywrightManager:
        async def __aenter__(self):
            return _PlaywrightStub()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    send_complete = AsyncMock()
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _DbSessionManager())
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task", AsyncMock())
    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: SimpleNamespace(load_account_async=AsyncMock(return_value={"account_id": "acc-1"})),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.CollectionExecutorV2",
        _ExecutorStub,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.browser_config_helper.get_browser_launch_args",
        lambda debug_mode=False: {},
    )
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: _PlaywrightManager())
    monkeypatch.setattr("backend.routers.collection_tasks.connection_manager.send_complete", send_complete)

    await _execute_collection_task_background(
        task_id=task.task_id,
        platform=task.platform,
        account_id=task.account,
        data_domains=["orders"],
        sub_domains={"orders": ["tiktok"]},
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        granularity="daily",
        debug_mode=False,
        parallel_mode=False,
        max_parallel=1,
        runtime_manifests={},
        app=None,
    )

    send_complete.assert_awaited_once_with(
        task.task_id,
        "completed",
        files_collected=1,
        error_message=None,
    )


@pytest.mark.asyncio
async def test_retry_task_requeues_background_execution(monkeypatch):
    from backend.routers.collection_tasks import retry_task

    original_task = _make_task(
        task_id="task-original",
        status="failed",
        trigger_type="manual",
        data_domains=["orders"],
        sub_domains={"orders": ["tiktok"]},
        granularity="daily",
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        retry_count=0,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = original_task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 2
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=_refresh)

    class _FakeResolver:
        @classmethod
        def from_async_session(cls, _db):
            return cls()

        async def resolve_task_manifests(self, **kwargs):
            return {"login": {}, "exports": [], "exports_by_domain": {}}

    scheduled = {}

    def _capture_background_task(coro):
        scheduled["coroutine_name"] = getattr(coro, "__name__", type(coro).__name__)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.ComponentRuntimeResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.routers.collection_tasks.asyncio.create_task",
        _capture_background_task,
    )
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task", AsyncMock())
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task_log", AsyncMock())

    request = SimpleNamespace(app=SimpleNamespace())

    body = await retry_task(
        task_id="task-original",
        request=request,
        db=db,
    )

    assert body["status"] == "pending"
    assert body["trigger_type"] == "retry"
    assert scheduled["coroutine_name"] == "_execute_collection_task_background"
