from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.routers.collection_tasks import cancel_or_delete_task, resume_task
from backend.schemas.collection import ResumeTaskRequest


def _make_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        task_id="task-1",
        platform="miaoshou",
        account="acc-1",
        status="verification_required",
        progress=40,
        current_step="等待验证码",
        files_collected=0,
        trigger_type="manual",
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        time_selection=None,
        total_domains=1,
        completed_domains=[],
        failed_domains=[],
        current_domain="orders",
        debug_mode=False,
        error_message=None,
        duration_seconds=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        verification_type="graphical_captcha",
        verification_screenshot="temp/task.png",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_resume_task_updates_status_to_verification_submitted():
    task = _make_task()

    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    redis = MagicMock()
    redis.set = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    body = await resume_task(
        task_id="task-1",
        body=ResumeTaskRequest(captcha_code="1234"),
        request=request,
        db=db,
    )

    assert task.status == "verification_submitted"
    assert body["status"] == "verification_submitted"
    assert body["verification_type"] == "graphical_captcha"
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_task_accepts_manual_completed_for_slide_captcha():
    task = _make_task(verification_type="slide_captcha")

    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    redis = MagicMock()
    redis.set = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    body = await resume_task(
        task_id="task-1",
        body=ResumeTaskRequest(manual_completed=True),
        request=request,
        db=db,
    )

    assert task.status == "verification_submitted"
    assert body["verification_type"] == "slide_captcha"
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_task_accepts_manual_intervention_required_status():
    task = _make_task(
        status="manual_intervention_required",
        verification_type="manual_intervention",
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    redis = MagicMock()
    redis.set = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    body = await resume_task(
        task_id="task-1",
        body=ResumeTaskRequest(manual_completed=True),
        request=request,
        db=db,
    )

    assert task.status == "verification_submitted"
    assert body["verification_type"] == "manual_intervention"
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_task_allows_verification_required_status(monkeypatch):
    task = _make_task(status="verification_required")

    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    mirror_task = AsyncMock()
    mirror_log = AsyncMock()
    delete_task_center = AsyncMock()

    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task", mirror_task)
    monkeypatch.setattr("backend.routers.collection_tasks._mirror_collection_task_log", mirror_log)

    class _TaskCenterService:
        def __init__(self, _db):
            self.db = _db

        async def delete_task(self, task_id):
            await delete_task_center(task_id)

    monkeypatch.setattr("backend.routers.collection_tasks.TaskCenterService", _TaskCenterService)

    body = await cancel_or_delete_task(task_id="task-1", db=db)

    assert task.status == "cancelled"
    assert task.error_message == "用户取消"
    assert body.success is True
    db.commit.assert_awaited_once()
    mirror_task.assert_awaited()
    mirror_log.assert_awaited()


@pytest.mark.asyncio
async def test_on_verification_required_broadcasts_websocket_event(monkeypatch):
    from backend.routers.collection_tasks import _on_verification_required

    task = _make_task()

    result = MagicMock()
    result.scalar_one_or_none.return_value = task

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    broadcast = AsyncMock()
    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal",
        lambda: _SessionManager(),
    )
    monkeypatch.setattr(
        "backend.routers.collection_tasks.connection_manager.send_verification_required",
        broadcast,
    )

    app = SimpleNamespace(state=SimpleNamespace(redis=None))
    value = await _on_verification_required(
        task_id="task-1",
        verification_type="graphical_captcha",
        screenshot_path="temp/task.png",
        app=app,
    )

    assert value is None
    assert task.status == "verification_required"
    broadcast.assert_awaited_once_with(
        "task-1",
        "graphical_captcha",
        "temp/task.png",
    )


@pytest.mark.asyncio
async def test_on_verification_required_marks_manual_continue_types_as_manual_intervention(monkeypatch):
    from backend.routers.collection_tasks import _on_verification_required

    task = _make_task(verification_type=None, status="running")

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

    broadcast = AsyncMock()
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _SessionManager())
    monkeypatch.setattr(
        "backend.routers.collection_tasks.connection_manager.send_verification_required",
        broadcast,
    )

    app = SimpleNamespace(state=SimpleNamespace(redis=None))
    value = await _on_verification_required(
        task_id="task-1",
        verification_type="slide_captcha",
        screenshot_path="temp/task.png",
        app=app,
    )

    assert value is None
    assert task.status == "manual_intervention_required"
