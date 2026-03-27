from types import SimpleNamespace

import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncDb:
    def __init__(self, file_record=None):
        self.file_record = file_record

    async def execute(self, _stmt):
        return _FakeScalarResult(self.file_record)


class _FakeProgressTracker:
    def __init__(self, task=None, tasks=None):
        self.task = task
        self.tasks = tasks or []

    async def get_task(self, task_id):
        if self.task and self.task.get("task_id") == task_id:
            return self.task
        return None

    async def list_tasks(self, status=None):
        if status is None:
            return list(self.tasks)
        return [task for task in self.tasks if task.get("status") == status]


@pytest.mark.asyncio
async def test_auto_ingest_task_logs_use_progress_tracker(monkeypatch):
    from backend.routers import auto_ingest

    monkeypatch.setattr(
        auto_ingest,
        "progress_tracker",
        _FakeProgressTracker(
            task={
                "task_id": "legacy-task",
                "task_type": "auto_ingest",
                "status": "completed",
                "files": [
                    {
                        "file_id": 11,
                        "file_name": "orders.xlsx",
                        "status": "success",
                        "staged": 12,
                        "imported": 12,
                        "quarantined": 0,
                    },
                    {
                        "file_id": 12,
                        "file_name": "products.xlsx",
                        "status": "failed",
                        "message": "header changed",
                    },
                ],
                "errors": [{"message": "batch warning"}],
            }
        ),
    )

    result = await auto_ingest.get_task_logs("legacy-task", limit=10, db=_FakeAsyncDb())

    assert result["success"] is True
    assert result["task_id"] == "legacy-task"
    assert result["total"] == 2
    assert result["logs"][0]["file_id"] == 11
    assert result["logs"][0]["imported"] == 12
    assert result["logs"][1]["file_id"] == 12
    assert result["logs"][1]["error_message"] == "header changed"


@pytest.mark.asyncio
async def test_auto_ingest_file_logs_use_progress_tracker(monkeypatch):
    from backend.routers import auto_ingest

    monkeypatch.setattr(
        auto_ingest,
        "progress_tracker",
        _FakeProgressTracker(
            tasks=[
                {
                    "task_id": "task-a",
                    "task_type": "auto_ingest",
                    "status": "completed",
                    "start_time": "2026-03-27T10:00:00",
                    "end_time": "2026-03-27T10:00:10",
                    "files": [
                        {
                            "file_id": 21,
                            "file_name": "inventory.xlsx",
                            "status": "success",
                            "staged": 8,
                            "imported": 8,
                            "quarantined": 0,
                        }
                    ],
                },
                {
                    "task_id": "task-b",
                    "task_type": "auto_ingest",
                    "status": "failed",
                    "start_time": "2026-03-27T11:00:00",
                    "end_time": "2026-03-27T11:00:05",
                    "files": [
                        {
                            "file_id": 21,
                            "file_name": "inventory.xlsx",
                            "status": "failed",
                            "message": "import failed",
                        }
                    ],
                },
            ]
        ),
    )

    db = _FakeAsyncDb(
        file_record=SimpleNamespace(
            id=21,
            file_name="inventory.xlsx",
            data_domain="inventory",
            status="failed",
            error_message="import failed",
        )
    )

    result = await auto_ingest.get_file_logs(21, limit=10, db=db)

    assert result["success"] is True
    assert result["file_id"] == 21
    assert result["total"] == 2
    assert result["logs"][0]["task_id"] == "task-a"
    assert result["logs"][1]["task_id"] == "task-b"
    assert result["logs"][1]["error_message"] == "import failed"
