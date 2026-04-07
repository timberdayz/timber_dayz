from types import SimpleNamespace

import pytest


class _FakeProgressTracker:
    def __init__(self):
        self.created = []
        self.updated = []
        self.completed = []

    async def create_task(self, task_id, total_files, task_type="bulk_ingest"):
        self.created.append((task_id, total_files, task_type))
        return {"task_id": task_id}

    async def update_task(self, task_id, updates):
        self.updated.append((task_id, updates))
        return {"task_id": task_id, **updates}

    async def complete_task(self, task_id, success=True, error=None):
        self.completed.append((task_id, success, error))
        return {"task_id": task_id, "success": success, "error": error}


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_legacy_orchestrator_single_delegates_to_data_sync_service(monkeypatch):
    from backend.services import auto_ingest_orchestrator as legacy_module

    captured = {}

    class FakeDataSyncService:
        def __init__(self, db):
            captured["db"] = db

        async def sync_single_file(
            self,
            file_id,
            only_with_template=True,
            allow_quarantine=True,
            task_id=None,
            use_template_header_row=True,
        ):
            captured["call"] = {
                "file_id": file_id,
                "only_with_template": only_with_template,
                "allow_quarantine": allow_quarantine,
                "task_id": task_id,
                "use_template_header_row": use_template_header_row,
            }
            return {"success": True, "file_id": file_id, "status": "success"}

    monkeypatch.setattr(legacy_module, "DataSyncService", FakeDataSyncService, raising=False)
    monkeypatch.setattr(legacy_module, "progress_tracker", _FakeProgressTracker(), raising=False)
    monkeypatch.setattr(legacy_module, "get_template_matcher", lambda _db: object(), raising=False)

    orchestrator = legacy_module.AutoIngestOrchestrator(object())
    result = await orchestrator.ingest_single_file(
        file_id=9,
        only_with_template=False,
        allow_quarantine=False,
        task_id="legacy-task",
    )

    assert result["success"] is True
    assert captured["call"] == {
        "file_id": 9,
        "only_with_template": False,
        "allow_quarantine": False,
        "task_id": "legacy-task",
        "use_template_header_row": True,
    }


@pytest.mark.asyncio
async def test_legacy_orchestrator_batch_delegates_and_summarizes(monkeypatch):
    from backend.services import auto_ingest_orchestrator as legacy_module

    progress = _FakeProgressTracker()
    seen_calls = []

    class FakeAsyncDb:
        async def execute(self, _stmt):
            return _FakeScalarResult(
                [
                    SimpleNamespace(id=1),
                    SimpleNamespace(id=2),
                ]
            )

    class FakeDataSyncService:
        def __init__(self, db):
            self.db = db

        async def sync_single_file(
            self,
            file_id,
            only_with_template=True,
            allow_quarantine=True,
            task_id=None,
            use_template_header_row=True,
        ):
            seen_calls.append((file_id, only_with_template, allow_quarantine, task_id, use_template_header_row))
            if file_id == 1:
                return {"success": True, "file_id": 1, "status": "success"}
            return {
                "success": False,
                "file_id": 2,
                "status": "skipped",
                "message": "no_template",
            }

    monkeypatch.setattr(legacy_module, "DataSyncService", FakeDataSyncService, raising=False)
    monkeypatch.setattr(legacy_module, "progress_tracker", progress, raising=False)
    monkeypatch.setattr(legacy_module, "get_template_matcher", lambda _db: object(), raising=False)

    orchestrator = legacy_module.AutoIngestOrchestrator(FakeAsyncDb())
    result = await orchestrator.batch_ingest(
        platform="*",
        domains=None,
        granularities=None,
        since_hours=None,
        limit=10,
        only_with_template=True,
        allow_quarantine=True,
    )

    assert result["success"] is True
    assert result["summary"]["total_files"] == 2
    assert result["summary"]["succeeded"] == 1
    assert result["summary"]["skipped_no_template"] == 1
    assert len(seen_calls) == 2
    assert progress.created and progress.completed
