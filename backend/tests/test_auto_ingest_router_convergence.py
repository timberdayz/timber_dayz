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
async def test_auto_ingest_single_route_uses_data_sync_service(monkeypatch):
    from backend.routers import auto_ingest
    from backend.schemas.auto_ingest import SingleAutoIngestRequest

    progress = _FakeProgressTracker()
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
            return {
                "success": True,
                "file_id": file_id,
                "file_name": "demo.xlsx",
                "status": "success",
                "message": "ok",
            }

    monkeypatch.setattr(auto_ingest, "progress_tracker", progress)
    monkeypatch.setattr(auto_ingest, "DataSyncService", FakeDataSyncService, raising=False)
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_orchestrator",
        lambda _db: (_ for _ in ()).throw(AssertionError("legacy orchestrator should not be used")),
        raising=False,
    )

    response = await auto_ingest.auto_ingest_single_file(
        SingleAutoIngestRequest(file_id=42, only_with_template=True, allow_quarantine=True),
        db=object(),
    )

    assert response["success"] is True
    assert response["file_id"] == 42
    assert response["status"] == "success"
    assert "task_id" in response
    assert captured["call"]["file_id"] == 42
    assert captured["call"]["use_template_header_row"] is True
    assert progress.created and progress.completed


@pytest.mark.asyncio
async def test_auto_ingest_batch_route_uses_data_sync_service(monkeypatch):
    from backend.routers import auto_ingest
    from backend.schemas.auto_ingest import BatchAutoIngestRequest

    progress = _FakeProgressTracker()
    seen_calls = []

    class FakeAsyncDb:
        async def execute(self, _stmt):
            return _FakeScalarResult(
                [
                    SimpleNamespace(id=1, first_seen_at=None),
                    SimpleNamespace(id=2, first_seen_at=None),
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
                return {
                    "success": True,
                    "file_id": file_id,
                    "file_name": "one.xlsx",
                    "status": "success",
                    "message": "ok",
                }
            return {
                "success": False,
                "file_id": file_id,
                "file_name": "two.xlsx",
                "status": "skipped",
                "message": "no_template",
            }

    monkeypatch.setattr(auto_ingest, "progress_tracker", progress)
    monkeypatch.setattr(auto_ingest, "DataSyncService", FakeDataSyncService, raising=False)
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_orchestrator",
        lambda _db: (_ for _ in ()).throw(AssertionError("legacy orchestrator should not be used")),
        raising=False,
    )

    response = await auto_ingest.auto_ingest_batch(
        BatchAutoIngestRequest(limit=10, only_with_template=True, allow_quarantine=True),
        db=FakeAsyncDb(),
    )

    assert response["success"] is True
    assert response["summary"]["total_files"] == 2
    assert response["summary"]["succeeded"] == 1
    assert response["summary"]["skipped_no_template"] == 1
    assert len(seen_calls) == 2
    assert progress.created and progress.completed
