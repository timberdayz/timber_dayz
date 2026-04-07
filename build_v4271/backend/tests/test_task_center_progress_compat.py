import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base


@pytest_asyncio.fixture
async def task_center_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
def task_center_session_factory(task_center_engine):
    return async_sessionmaker(task_center_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def task_center_async_client():
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
async def test_legacy_progress_tracker_survives_process_restart(task_center_session_factory):
    from backend.services.progress_tracker import ProgressTracker

    tracker = ProgressTracker(async_session_factory=task_center_session_factory)
    await tracker.create_task("legacy-1", 1, "bulk_ingest")

    reloaded = ProgressTracker(async_session_factory=task_center_session_factory)
    task = await reloaded.get_task("legacy-1")

    assert task["task_id"] == "legacy-1"


@pytest.mark.asyncio
async def test_field_mapping_progress_endpoint_keeps_legacy_shape(
    task_center_session_factory,
    task_center_async_client,
    monkeypatch,
):
    from backend.routers import field_mapping_status
    from backend.services.progress_tracker import ProgressTracker

    tracker = ProgressTracker(async_session_factory=task_center_session_factory)
    await tracker.create_task("legacy-route-1", 2, "bulk_ingest")
    await tracker.update_task(
        "legacy-route-1",
        {
            "status": "processing",
            "processed_files": 1,
            "total_rows": 5,
            "processed_rows": 3,
            "custom_counter": 7,
        },
    )

    monkeypatch.setattr(field_mapping_status, "progress_tracker", tracker)

    response = await task_center_async_client.get("/api/field-mapping/progress/legacy-route-1")

    assert response.status_code == 200
    payload = response.json()["data"]["progress"]
    assert payload["task_id"] == "legacy-route-1"
    assert payload["processed_files"] == 1
    assert payload["custom_counter"] == 7
