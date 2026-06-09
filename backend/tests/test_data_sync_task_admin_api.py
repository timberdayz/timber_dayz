import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CatalogFile, TaskCenterTask


@pytest_asyncio.fixture
async def task_admin_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: TaskCenterTask.metadata.create_all(
                sync_conn,
                tables=[TaskCenterTask.__table__, CatalogFile.__table__],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def task_admin_client(task_admin_session):
    from backend.main import app
    from backend.dependencies.auth import require_admin
    from backend.models.database import get_async_db

    class _AdminUser:
        id = 1
        username = "admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_admin():
        return _AdminUser()

    async def override_db():
        yield task_admin_session

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[require_admin] = override_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, task_admin_session

    app.dependency_overrides.clear()


async def _seed_running_auto_ingest(session, *, task_id: str, status: str = "running"):
    task = TaskCenterTask(
        task_id=task_id,
        task_family="data_sync",
        task_type="auto_ingest",
        status=status,
        total_items=1,
        processed_items=0,
        success_items=0,
        failed_items=0,
        skipped_items=0,
        progress_percent=0.0,
        details_json={"errors": [], "warnings": [], "message": None, "task_details": {"file_ids": [101]}},
    )
    file_row = CatalogFile(
        id=101,
        file_name="sample.xlsx",
        file_path="data/raw/sample.xlsx",
        platform_code="shopee",
        source_platform="shopee",
        data_domain="services",
        granularity="monthly",
        sub_domain="agent",
        status="processing",
        file_metadata={
            "auto_ingest": {
                "current_task_id": task_id,
                "processing_started_at": "2026-06-09T10:00:00+00:00",
                "claimed_by": "scheduled_tasks.auto_ingest_pending_files",
                "last_status": "claimed",
            }
        },
    )
    session.add(task)
    session.add(file_row)
    await session.commit()


@pytest.mark.asyncio
async def test_cancel_auto_ingest_task_marks_task_cancelled_and_requeues_files(task_admin_client):
    client, session = task_admin_client
    await _seed_running_auto_ingest(session, task_id="auto-ingest-cancel-1")

    response = await client.post("/api/data-sync/tasks/auto-ingest-cancel-1/cancel")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "auto-ingest-cancel-1"
    assert payload["status_before"] == "running"
    assert payload["status_after"] == "cancelled"
    assert payload["recovered_file_count"] == 1

    task = (
        await session.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == "auto-ingest-cancel-1")
        )
    ).scalar_one()
    file_row = (await session.execute(select(CatalogFile).where(CatalogFile.id == 101))).scalar_one()

    assert task.status == "cancelled"
    assert task.error_summary == "cancelled by user"
    assert file_row.status == "pending"
    assert file_row.file_metadata["auto_ingest"]["last_status"] == "cancelled"
    assert file_row.file_metadata["auto_ingest"]["current_task_id"] is None


@pytest.mark.asyncio
async def test_recover_auto_ingest_task_marks_task_failed_and_requeues_files(task_admin_client):
    client, session = task_admin_client
    await _seed_running_auto_ingest(session, task_id="auto-ingest-recover-1")

    response = await client.post("/api/data-sync/tasks/auto-ingest-recover-1/recover")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status_before"] == "running"
    assert payload["status_after"] == "failed"
    assert payload["recovered_file_count"] == 1

    task = (
        await session.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == "auto-ingest-recover-1")
        )
    ).scalar_one()
    file_row = (await session.execute(select(CatalogFile).where(CatalogFile.id == 101))).scalar_one()

    assert task.status == "failed"
    assert task.error_summary == "force recovered by user"
    assert file_row.status == "pending"
    assert file_row.file_metadata["auto_ingest"]["last_status"] == "stale_recovered"


@pytest.mark.asyncio
async def test_cancel_auto_ingest_task_is_idempotent_for_terminal_status(task_admin_client):
    client, session = task_admin_client
    await _seed_running_auto_ingest(session, task_id="auto-ingest-cancelled-1", status="completed")

    response = await client.post("/api/data-sync/tasks/auto-ingest-cancelled-1/cancel")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status_before"] == "completed"
    assert payload["status_after"] == "completed"
    assert payload["recovered_file_count"] == 0
