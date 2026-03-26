from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.cloud_sync_admin_command_service import CloudSyncAdminCommandService
from modules.core.db import Base
from modules.core.db import CloudBClassSyncTask


@pytest_asyncio.fixture
async def cloud_sync_sqlite_session():
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
async def test_command_service_rejects_invalid_table_name(cloud_sync_sqlite_session):
    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)

    with pytest.raises(ValueError):
        await service.trigger_sync("orders")


@pytest.mark.asyncio
async def test_command_service_trigger_sync_creates_pending_task(cloud_sync_sqlite_session):
    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)

    payload = await service.trigger_sync("fact_tiktok_orders_daily")

    assert payload["status"] == "pending"
    assert payload["source_table_name"] == "fact_tiktok_orders_daily"


@pytest.mark.asyncio
async def test_command_service_can_retry_and_cancel_task(cloud_sync_sqlite_session):
    task = CloudBClassSyncTask(
        job_id="job-1",
        dedupe_key="fact_shopee_orders_daily",
        source_table_name="fact_shopee_orders_daily",
        status="failed",
        attempt_count=2,
        created_at=datetime.now(timezone.utc),
    )
    cloud_sync_sqlite_session.add(task)
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)

    retried = await service.retry_task("job-1")
    cancelled = await service.cancel_task("job-1")

    assert retried["status"] == "pending"
    assert cancelled["status"] == "cancelled"
