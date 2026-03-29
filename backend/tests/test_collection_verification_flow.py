from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.routers.collection_tasks import resume_task
from backend.schemas.collection import ResumeTaskRequest


def _make_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        task_id="task-1",
        platform="miaoshou",
        account="acc-1",
        status="paused",
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
