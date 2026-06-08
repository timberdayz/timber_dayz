import pytest


def _task_row(task_id, task_type, trigger_source=None):
    return {
        "task_id": task_id,
        "task_type": task_type,
        "trigger_source": trigger_source,
        "status": "completed",
        "total_items": 1,
        "processed_items": 1,
        "current_item": None,
        "total_rows": 0,
        "processed_rows": 0,
        "valid_rows": 0,
        "error_rows": 0,
        "quarantined_rows": 0,
        "progress_percent": 100.0,
        "started_at": None,
        "finished_at": None,
        "updated_at": None,
        "details_json": {
            "errors": [],
            "warnings": [],
            "message": None,
            "row_progress": 0.0,
            "task_details": {},
        },
    }


class _FakeTaskCenter:
    def __init__(self, rows):
        self.rows = rows

    async def list_tasks(self, **_kwargs):
        return self.rows


@pytest.mark.asyncio
async def test_list_tasks_returns_trigger_source_for_auto_and_manual_tasks():
    from backend.services.sync_progress_tracker import SyncProgressTracker

    tracker = object.__new__(SyncProgressTracker)
    tracker.task_center = _FakeTaskCenter(
        [
            _task_row("auto_ingest_20260608120000_abcdef12", "auto_ingest"),
            _task_row("single_file_101_abcdef12", "single_file"),
            _task_row("bulk_ingest_abcdef12", "bulk_ingest", ""),
            _task_row("single_file_102_abcdef12", "single_file", "sync_now"),
        ]
    )

    tasks = await tracker.list_tasks(limit=10)

    assert [task["trigger_source"] for task in tasks] == [
        "auto_ingest",
        "manual",
        "manual",
        "sync_now",
    ]
