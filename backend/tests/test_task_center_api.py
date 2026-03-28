import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.task_center_service import TaskCenterService
from modules.core.db import Base


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


@pytest_asyncio.fixture
async def seeded_task_center_data(task_center_sqlite_session):
    service = TaskCenterService(task_center_sqlite_session)
    await service.create_task(
        task_id="task-center-1",
        task_family="data_sync",
        task_type="single_file",
        status="running",
        platform_code="shopee",
    )
    await service.add_link(
        "task-center-1",
        subject_type="catalog_file",
        subject_id="1",
    )
    await service.append_log(
        "task-center-1",
        level="info",
        event_type="progress",
        message="seeded",
        details_json={"step": "seed"},
    )


@pytest.mark.asyncio
async def test_task_center_tasks_endpoint_supports_family_and_status_filters(
    task_center_async_client,
    seeded_task_center_data,
):
    response = await task_center_async_client.get(
        "/api/task-center/tasks?family=data_sync&status=running&page=1&page_size=20"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"][0]["task_id"] == "task-center-1"
    assert payload["items"][0]["task_family"] == "data_sync"


@pytest.mark.asyncio
async def test_task_center_can_lookup_tasks_by_catalog_file(
    task_center_async_client,
    seeded_task_center_data,
):
    response = await task_center_async_client.get(
        "/api/task-center/tasks/by-subject?subject_type=catalog_file&subject_id=1"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"][0]["task_id"] == "task-center-1"


@pytest.mark.asyncio
async def test_task_center_tasks_endpoint_reports_total_beyond_page_size(
    task_center_sqlite_session,
    task_center_async_client,
):
    service = TaskCenterService(task_center_sqlite_session)
    for index in range(3):
        await service.create_task(
            task_id=f"task-center-page-{index}",
            task_family="data_sync",
            task_type="single_file",
            status="running",
        )

    response = await task_center_async_client.get(
        "/api/task-center/tasks?family=data_sync&status=running&page=1&page_size=2"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload["items"]) == 2
    assert payload["total"] == 3
