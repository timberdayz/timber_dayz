from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, CatalogFile, TaskCenterTask


class _QuotaServiceStub:
    max_concurrent_tasks = 10

    async def can_submit_task(self, user_id):
        return True, None

    async def increment_user_task_count(self, user_id):
        return True


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


@pytest_asyncio.fixture
async def task_center_async_client(task_center_sqlite_session):
    from backend.dependencies.auth import get_current_user
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield task_center_sqlite_session

    async def override_current_user():
        # data_sync router 整体挂了 ``require_admin`` 依赖(``router = APIRouter(dependencies=[Depends(require_admin)])``),
        # 桩用户必须是管理员, 否则请求会被鉴权拦成 403。
        return SimpleNamespace(
            user_id=1,
            id=1,
            username="task-center-test",
            is_active=True,
            status="active",
            is_superuser=True,
            roles=[],
        )

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
async def test_single_sync_submission_persists_celery_runner_id(
    task_center_sqlite_session,
    task_center_async_client,
    seeded_catalog_file,
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.domains.data_platform.routers.data_sync.get_user_task_quota_service",
        lambda: _QuotaServiceStub(),
    )
    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="celery-task-1"),
    )

    response = await task_center_async_client.post(
        "/api/data-sync/single",
        json={"file_id": seeded_catalog_file.id},
    )

    assert response.status_code == 200
    payload = response.json()["data"]

    result = await task_center_sqlite_session.execute(
        select(TaskCenterTask).where(TaskCenterTask.task_id == payload["task_id"])
    )
    task = result.scalar_one()

    assert task.external_runner_id == "celery-task-1"
    assert task.runner_kind == "celery"


@pytest.mark.asyncio
async def test_task_center_stores_submission_metadata_for_retry(
    task_center_sqlite_session,
    task_center_async_client,
    seeded_catalog_file,
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.domains.data_platform.routers.data_sync.get_user_task_quota_service",
        lambda: _QuotaServiceStub(),
    )
    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="celery-task-2"),
    )

    response = await task_center_async_client.post(
        "/api/data-sync/single",
        json={"file_id": seeded_catalog_file.id},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["task_id"]

    result = await task_center_sqlite_session.execute(
        select(TaskCenterTask).where(TaskCenterTask.task_id == task_id)
    )
    task = result.scalar_one()

    assert (
        task.details_json["task_details"]["submission_args"]["file_id"]
        == seeded_catalog_file.id
    )
