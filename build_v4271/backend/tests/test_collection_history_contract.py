from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.routers.collection_tasks import get_history


def _make_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        task_id="task-history-1",
        platform="miaoshou",
        account="acc-1",
        status="completed",
        progress=100,
        current_step="done",
        files_collected=3,
        trigger_type="manual",
        config_id=42,
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range={"start_date": "2026-03-01", "end_date": "2026-03-01"},
        total_domains=1,
        completed_domains=["orders"],
        failed_domains=[],
        current_domain=None,
        debug_mode=False,
        error_message=None,
        duration_seconds=12,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
        verification_type=None,
        verification_screenshot=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_get_history_serializes_collection_tasks_with_task_response_contract():
    task = _make_task()

    class _CountResult:
        def scalar(self):
            return 1

    class _DataResult:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return [task]

            return _Scalars()

    class _FakeDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return _CountResult()
            return _DataResult()

    response = await get_history(
        platform=None,
        status=None,
        start_date=None,
        end_date=None,
        page=1,
        page_size=20,
        db=_FakeDb(),
    )

    assert response.total == 1
    assert response.page == 1
    assert len(response.data) == 1
    assert response.data[0].task_id == "task-history-1"
    assert response.data[0].execution_mode == "headless"
