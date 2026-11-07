import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.task_center_service import TaskCenterService
from modules.core.db import Base


# SQLite 建不了 ``a_class.operating_costs``: 它的 server_default 用了 postgres 专有的
# ``'[]'::jsonb`` 转型表达式, SQLite 解析不了(``unrecognized token: ":"``)。
# 这张表与 task-center 用例无关, 建表时跳过(做法同 test_price_adjust_notification.py)。
_SQLITE_UNSUPPORTED_TABLES = {("a_class", "operating_costs")}


def _sqlite_tables():
    """返回能在 SQLite 上建出来的表(排除 postgres 专有 DDL 的表)。"""
    return [
        table
        for table in Base.metadata.sorted_tables
        if (str(table.schema), table.name) not in _SQLITE_UNSUPPORTED_TABLES
    ]


@pytest_asyncio.fixture
async def task_center_sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in (
            "core",
            "a_class",
            "b_class",
            "c_class",
            "finance",
            "ops",
            "semantic",
        ):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_sqlite_tables()
            )
        )

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
