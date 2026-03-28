import pytest
import pytest_asyncio
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


@pytest.mark.asyncio
async def test_task_center_service_creates_task_and_log(task_center_sqlite_session):
    service = TaskCenterService(task_center_sqlite_session)

    task = await service.create_task(
        task_id="task-1",
        task_family="data_sync",
        task_type="single_file",
    )

    await service.append_log(
        "task-1",
        level="info",
        event_type="state_change",
        message="created",
    )

    loaded = await service.get_task("task-1")

    assert task["task_id"] == "task-1"
    assert loaded["task_id"] == "task-1"
    assert loaded["task_family"] == "data_sync"


@pytest.mark.asyncio
async def test_task_center_service_links_catalog_file(task_center_sqlite_session):
    service = TaskCenterService(task_center_sqlite_session)

    await service.create_task(
        task_id="task-1",
        task_family="data_sync",
        task_type="single_file",
    )

    await service.add_link(
        "task-1",
        subject_type="catalog_file",
        subject_id="42",
    )

    rows = await service.list_by_subject(
        subject_type="catalog_file",
        subject_id="42",
    )

    assert len(rows) == 1
    assert rows[0]["task_id"] == "task-1"
