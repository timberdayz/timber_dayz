from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.task_center_service import TaskCenterService
from modules.core.db import Base, CollectionTask


@pytest_asyncio.fixture
async def task_center_sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
def task_center_session_factory(task_center_sqlite_engine):
    return async_sessionmaker(task_center_sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def task_center_sqlite_session(task_center_session_factory):
    async with task_center_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_async_client(task_center_sqlite_session):
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield task_center_sqlite_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)


class _AccountLoaderStub:
    async def load_account_async(self, account_id, db):
        return {
            "account_id": account_id,
            "capabilities": {"orders": True},
        }


class _ResolverStub:
    async def resolve_task_manifests(self, **kwargs):
        return {"orders": {"component": "stub"}}


@pytest.mark.asyncio
async def test_collection_task_creation_writes_task_center_row(
    task_center_sqlite_session,
    monkeypatch,
):
    from backend.services import account_loader_service, component_runtime_resolver
    from backend.routers import collection_tasks
    from backend.routers.collection_tasks import create_task
    from backend.schemas.collection import TaskCreateRequest

    monkeypatch.setattr(
        account_loader_service,
        "get_account_loader_service",
        lambda: _AccountLoaderStub(),
    )
    monkeypatch.setattr(
        component_runtime_resolver.ComponentRuntimeResolver,
        "from_async_session",
        classmethod(lambda cls, db: _ResolverStub()),
    )

    def _swallow_background(coro, *args, **kwargs):
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(collection_tasks.asyncio, "create_task", _swallow_background)

    payload = await create_task(
        request=TaskCreateRequest(
            platform="shopee",
            account_id="acc-1",
            data_domains=["orders"],
            time_selection={"mode": "preset", "preset": "yesterday"},
        ),
        fastapi_request=SimpleNamespace(app=None),
        db=task_center_sqlite_session,
    )

    task_id = payload["task_id"]

    mirrored = await TaskCenterService(task_center_sqlite_session).get_task(task_id)

    assert mirrored is not None
    assert mirrored["task_family"] == "collection"
    assert mirrored["platform_code"] == "shopee"
    assert mirrored["account_id"] == "acc-1"


@pytest.mark.asyncio
async def test_collection_task_create_api_accepts_time_selection_payload(
    task_center_sqlite_session,
    collection_async_client,
    monkeypatch,
):
    from backend.services import account_loader_service, component_runtime_resolver
    from backend.routers import collection_tasks

    monkeypatch.setattr(
        account_loader_service,
        "get_account_loader_service",
        lambda: _AccountLoaderStub(),
    )
    monkeypatch.setattr(
        component_runtime_resolver.ComponentRuntimeResolver,
        "from_async_session",
        classmethod(lambda cls, db: _ResolverStub()),
    )

    async def _noop_background(**kwargs):
        return None

    monkeypatch.setattr(collection_tasks, "_execute_collection_task_background", _noop_background)

    response = await collection_async_client.post(
        "/api/collection/tasks",
        json={
            "platform": "shopee",
            "account_id": "acc-1",
            "data_domains": ["orders"],
            "time_selection": {
                "mode": "preset",
                "preset": "yesterday",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"]


@pytest.mark.asyncio
async def test_collection_task_log_is_mirrored_to_task_center(
    task_center_sqlite_session,
    task_center_session_factory,
    monkeypatch,
):
    from backend.models import database as database_module
    from backend.routers.collection_tasks import _collection_step_status_callback

    task = CollectionTask(
        task_id="collection-task-1",
        platform="shopee",
        account="acc-1",
        status="running",
        trigger_type="manual",
    )
    task_center_sqlite_session.add(task)
    await task_center_sqlite_session.commit()
    await task_center_sqlite_session.refresh(task)

    await TaskCenterService(task_center_sqlite_session).create_task(
        task_id=task.task_id,
        task_family="collection",
        task_type="manual",
        platform_code=task.platform,
        account_id=task.account,
    )

    monkeypatch.setattr(database_module, "AsyncSessionLocal", task_center_session_factory)

    await _collection_step_status_callback(
        task_id=task.task_id,
        progress=55,
        message="采集中",
        current_domain="orders",
        details={"step_id": "export_orders", "success": True},
    )

    logs = await TaskCenterService(task_center_sqlite_session).list_logs(task.task_id)

    assert len(logs) == 1
    assert logs[0]["message"] == "采集中"
    assert logs[0]["event_type"] == "progress"


@pytest.mark.asyncio
async def test_collection_background_failure_updates_task_center_status(
    task_center_sqlite_session,
    task_center_session_factory,
    monkeypatch,
):
    from backend.models import database as database_module
    from backend.routers.collection_tasks import _execute_collection_task_background
    from backend.services import account_loader_service

    task = CollectionTask(
        task_id="collection-task-bg-1",
        platform="shopee",
        account="acc-1",
        status="pending",
        trigger_type="manual",
    )
    task_center_sqlite_session.add(task)
    await task_center_sqlite_session.commit()
    await task_center_sqlite_session.refresh(task)

    await TaskCenterService(task_center_sqlite_session).create_task(
        task_id=task.task_id,
        task_family="collection",
        task_type="manual",
        status="pending",
        platform_code=task.platform,
        account_id=task.account,
    )

    class _MissingAccountLoader:
        async def load_account_async(self, account_id, db):
            return None

    monkeypatch.setattr(database_module, "AsyncSessionLocal", task_center_session_factory)
    monkeypatch.setattr(
        account_loader_service,
        "get_account_loader_service",
        lambda: _MissingAccountLoader(),
    )

    await _execute_collection_task_background(
        task_id=task.task_id,
        platform=task.platform,
        account_id=task.account,
        data_domains=["orders"],
        sub_domains=None,
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        granularity="daily",
        debug_mode=False,
        parallel_mode=False,
        max_parallel=1,
        runtime_manifests={},
        app=None,
    )

    mirrored = await TaskCenterService(task_center_sqlite_session).get_task(task.task_id)

    assert mirrored["status"] == "failed"
