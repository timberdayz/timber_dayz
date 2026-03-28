import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.sync_progress_tracker import SyncProgressTracker
from modules.core.db import Base, TaskCenterTask


@pytest_asyncio.fixture
async def task_center_sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def task_center_async_client(task_center_sqlite_session):
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield task_center_sqlite_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.asyncio
async def test_sync_progress_tracker_uses_task_center_storage(task_center_sqlite_session):
    tracker = SyncProgressTracker(task_center_sqlite_session)

    await tracker.create_task(task_id="sync-1", total_files=2, task_type="bulk_ingest")

    result = await task_center_sqlite_session.execute(
        select(TaskCenterTask).where(TaskCenterTask.task_id == "sync-1")
    )
    task = result.scalar_one_or_none()

    assert task is not None
    assert task.task_id == "sync-1"
    assert task.task_family == "data_sync"


@pytest.mark.asyncio
async def test_data_sync_progress_endpoint_keeps_legacy_shape(
    task_center_sqlite_session,
    task_center_async_client,
):
    tracker = SyncProgressTracker(task_center_sqlite_session)
    await tracker.create_task(task_id="sync-route-1", total_files=2, task_type="bulk_ingest")
    await tracker.update_task(
        "sync-route-1",
        {
            "status": "processing",
            "processed_files": 1,
            "task_details": {"success_files": 1},
        },
    )

    response = await task_center_async_client.get("/api/data-sync/progress/sync-route-1")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "sync-route-1"
    assert "file_progress" in payload
    assert "success_files" in payload
