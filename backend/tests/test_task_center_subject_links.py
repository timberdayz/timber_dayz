from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.task_center_service import TaskCenterService
from modules.core.db import Base, CatalogFile


class _QuotaServiceStub:
    max_concurrent_tasks = 10

    async def can_submit_task(self, user_id):
        return True, None

    async def increment_user_task_count(self, user_id):
        return True


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
    from backend.dependencies.auth import get_current_user
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield task_center_sqlite_session

    async def override_current_user():
        return SimpleNamespace(user_id=1, id=1, username="task-center-test")

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seeded_catalog_file(task_center_sqlite_session):
    file_record = CatalogFile(
        id=1,
        file_path="data/raw/2026/orders.xlsx",
        file_name="orders.xlsx",
        status="pending",
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
    )
    task_center_sqlite_session.add(file_record)
    await task_center_sqlite_session.commit()
    return file_record


@pytest.mark.asyncio
async def test_data_sync_task_links_catalog_file(
    task_center_sqlite_session,
    task_center_async_client,
    seeded_catalog_file,
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.routers.data_sync.get_user_task_quota_service",
        lambda: _QuotaServiceStub(),
    )
    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="celery-task-link-1"),
    )

    response = await task_center_async_client.post(
        "/api/data-sync/single",
        json={"file_id": seeded_catalog_file.id},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["task_id"]

    rows = await TaskCenterService(task_center_sqlite_session).list_by_subject(
        subject_type="catalog_file",
        subject_id=str(seeded_catalog_file.id),
    )

    assert len(rows) == 1
    assert rows[0]["task_id"] == task_id


@pytest.mark.asyncio
async def test_task_center_lists_tasks_for_source_table(
    task_center_sqlite_session,
    task_center_async_client,
    seeded_catalog_file,
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.routers.data_sync.get_user_task_quota_service",
        lambda: _QuotaServiceStub(),
    )
    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="celery-task-link-2"),
    )

    response = await task_center_async_client.post(
        "/api/data-sync/single",
        json={"file_id": seeded_catalog_file.id},
    )

    assert response.status_code == 200
    rows = await TaskCenterService(task_center_sqlite_session).list_by_subject(
        subject_type="source_table",
        subject_key="fact_shopee_orders_daily",
    )

    assert len(rows) == 1
