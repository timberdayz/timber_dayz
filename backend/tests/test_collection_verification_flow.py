from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.routers.collection_tasks import cancel_or_delete_task, resume_task
from backend.schemas.collection import ResumeTaskRequest


class _AsyncioProxy:
    """只拦指定 asyncio 成员，其余透传——避免直接改全局 asyncio 模块。"""

    def __init__(self, real_module, **overrides):
        self._real = real_module
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


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


class _FakeQueryResult:
    """按查询目标区分返回值：任务中心表无记录，采集任务返回假任务。"""

    def __init__(self, task=None):
        self._task = task

    def scalar_one_or_none(self):
        return self._task

    def scalars(self):
        return self

    def all(self):
        return []


def _make_fake_db_session(task):
    """假 session：任务中心表查询返回空，采集任务/目录文件查询返回假任务。"""

    class _FakeDbSession:
        def __init__(self):
            self.execute = AsyncMock(side_effect=self._execute)
            self.commit = AsyncMock()
            self.rollback = AsyncMock()
            self.refresh = AsyncMock()
            self.add = MagicMock()

        async def _execute(self, stmt):
            if "task_center_tasks" in str(stmt):
                return _FakeQueryResult(None)
            return _FakeQueryResult(task)

    return _FakeDbSession()


class _FakeTaskCenterService:
    """路由层 TaskCenterService 替身：任务中心记录不在本次断言范围内。"""

    def __init__(self, _db):
        self.db = _db

    async def get_task(self, _task_id):
        return None

    async def create_task(self, **_fields):
        return {}

    async def update_task(self, _task_id, **_updates):
        return {}


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

    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks._mirror_collection_task",
        mirror_task,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks._mirror_collection_task_log",
        mirror_log,
    )

    class _TaskCenterService:
        def __init__(self, _db):
            self.db = _db

        async def delete_task(self, task_id):
            await delete_task_center(task_id)

    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.TaskCenterService",
        _TaskCenterService,
    )

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
        "backend.domains.collection.routers.collection_tasks.connection_manager.send_verification_required",
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
    assert task.current_step == "等待验证码回填"
    broadcast.assert_awaited_once_with(
        "task-1",
        "graphical_captcha",
        "temp/task.png",
    )


@pytest.mark.asyncio
async def test_on_verification_required_marks_manual_continue_types_as_manual_intervention(
    monkeypatch,
):
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
    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal", lambda: _SessionManager()
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.connection_manager.send_verification_required",
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
    assert task.current_step == "等待人工处理"


@pytest.mark.asyncio
async def test_on_verification_required_stops_waiting_when_task_cancelled(monkeypatch):
    from backend.routers.collection_tasks import _on_verification_required

    task = _make_task(status="running")

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

    class _FakeLoop:
        def __init__(self):
            self.now = 0.0

        def time(self):
            return self.now

    fake_loop = _FakeLoop()

    async def _fake_sleep(seconds):
        fake_loop.now += seconds

    redis = MagicMock()
    redis.delete = AsyncMock()
    get_calls = {"count": 0}

    async def _fake_get(_key):
        get_calls["count"] += 1
        if get_calls["count"] == 1:
            task.status = "cancelled"
        return None

    redis.get = AsyncMock(side_effect=_fake_get)

    mirror_task = AsyncMock()
    broadcast = AsyncMock()

    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal", lambda: _SessionManager()
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks._mirror_collection_task",
        mirror_task,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.connection_manager.send_verification_required",
        broadcast,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.asyncio",
        _AsyncioProxy(
            asyncio,
            sleep=_fake_sleep,
            get_running_loop=lambda: fake_loop,
        ),
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.VERIFICATION_WAIT_TIMEOUT",
        0.3,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.VERIFICATION_POLL_INTERVAL",
        0.1,
    )

    app = SimpleNamespace(state=SimpleNamespace(redis=redis))
    value = await _on_verification_required(
        task_id="task-1",
        verification_type="graphical_captcha",
        screenshot_path="temp/task.png",
        app=app,
    )

    assert value is None
    assert get_calls["count"] == 1


@pytest.mark.asyncio
async def test_get_task_screenshot_resolves_relative_path_from_project_root(
    tmp_path, monkeypatch
):
    from backend.domains.collection.routers import (
        collection_tasks as domain_collection_tasks,
    )

    task = _make_task(
        verification_screenshot="temp/screenshots/task-1/captcha.png",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    project_root = tmp_path / "repo"
    screenshot_path = project_root / "temp" / "screenshots" / "task-1" / "captcha.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_bytes(b"fake-image")

    fake_router_file = (
        project_root
        / "backend"
        / "domains"
        / "collection"
        / "routers"
        / "collection_tasks.py"
    )
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# stub", encoding="utf-8")

    monkeypatch.setattr(domain_collection_tasks, "__file__", str(fake_router_file))

    response = await domain_collection_tasks.get_task_screenshot(
        task_id="task-1",
        db=db,
    )

    assert str(response.path) == str(screenshot_path)


@pytest.mark.asyncio
async def test_persist_collection_task_result_clears_verification_fields_on_terminal_status(
    monkeypatch,
):
    from backend.domains.collection.routers.collection_tasks import (
        _persist_collection_task_result,
    )

    task = _make_task(
        status="verification_required",
        verification_type="graphical_captcha",
        verification_screenshot="temp/task.png",
    )

    db_session = _make_fake_db_session(task)

    class _DbSessionManager:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.TaskCenterService",
        _FakeTaskCenterService,
    )

    from backend.models import database as database_module

    original_async_session_local = database_module.AsyncSessionLocal
    database_module.AsyncSessionLocal = lambda: _DbSessionManager()
    try:
        final_result = SimpleNamespace(
            status="completed",
            files_collected=1,
            error_message=None,
            duration_seconds=12,
            completed_domains=["orders"],
            failed_domains=[],
        )

        persisted = await _persist_collection_task_result("task-1", final_result)
    finally:
        database_module.AsyncSessionLocal = original_async_session_local

    assert persisted is task
    assert task.verification_type is None
    assert task.verification_screenshot is None


@pytest.mark.asyncio
async def test_persist_collection_task_result_preserves_cancelled_status(monkeypatch):
    from backend.domains.collection.routers.collection_tasks import (
        _persist_collection_task_result,
    )
    from modules.core.db import CollectionTask
    import backend.models.database as database_module

    stored_task = CollectionTask(
        id=1,
        task_id="task-cancelled",
        platform="shopee",
        account="acc-1",
        status="cancelled",
        trigger_type="manual",
        files_collected=0,
    )

    db_session = _make_fake_db_session(stored_task)

    class _DbSessionManager:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.domains.collection.routers.collection_tasks.TaskCenterService",
        _FakeTaskCenterService,
    )

    final_result = SimpleNamespace(
        status="completed",
        files_collected=3,
        error_message=None,
        duration_seconds=10,
        completed_domains=["orders"],
        failed_domains=[],
    )

    original_async_session_local = database_module.AsyncSessionLocal
    database_module.AsyncSessionLocal = lambda: _DbSessionManager()
    try:
        persisted = await _persist_collection_task_result(
            "task-cancelled", final_result
        )
    finally:
        database_module.AsyncSessionLocal = original_async_session_local

    assert persisted.status == "cancelled"
    assert persisted.files_collected == 0
