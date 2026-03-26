from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.cloud_sync_admin_command_service import CloudSyncAdminCommandService
from modules.core.db import Base
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask


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


@pytest.mark.asyncio
async def test_command_service_dry_run_executes_sync_table(monkeypatch, cloud_sync_sqlite_session):
    class FakeSyncService:
        async def sync_table(self, table_name: str, batch_size: int = 1000):
            return {
                "status": "completed",
                "table_name": table_name,
                "written_rows": 0,
                "dry_run": True,
            }

        def close(self):
            return None

    monkeypatch.setattr(
        "backend.services.cloud_sync_admin_command_service.build_cloud_sync_service_from_env",
        lambda dry_run=False: FakeSyncService(),
    )

    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)
    payload = await service.dry_run_table("fact_tiktok_orders_daily")

    assert payload["status"] == "completed"
    assert payload["source_table_name"] == "fact_tiktok_orders_daily"
    assert payload["detail"] == "dry_run"


@pytest.mark.asyncio
async def test_command_service_repair_checkpoint_resets_checkpoint(cloud_sync_sqlite_session):
    checkpoint = CloudBClassSyncCheckpoint(
        table_schema="cloud_sync:test-scope",
        table_name="fact_shopee_orders_daily",
        last_source_id=123,
        last_status="failed",
        last_error="boom",
    )
    cloud_sync_sqlite_session.add(checkpoint)
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)
    payload = await service.repair_checkpoint("fact_shopee_orders_daily")

    refreshed = await cloud_sync_sqlite_session.get(CloudBClassSyncCheckpoint, checkpoint.id)

    assert payload["status"] == "repaired"
    assert refreshed.last_source_id is None
    assert refreshed.last_status == "pending"
    assert refreshed.last_error is None


@pytest.mark.asyncio
async def test_command_service_refresh_projection_executes_refresh_plan(monkeypatch, cloud_sync_sqlite_session):
    calls = {}

    async def fake_execute_refresh_plan(db, targets, pipeline_name, trigger_source, context, continue_on_error, max_attempts, retry_backoff_seconds):
        calls["targets"] = targets
        calls["pipeline_name"] = pipeline_name
        calls["trigger_source"] = trigger_source
        calls["context"] = context
        return "run-1"

    monkeypatch.setattr(
        "backend.services.cloud_sync_admin_command_service.execute_refresh_plan",
        fake_execute_refresh_plan,
    )

    service = CloudSyncAdminCommandService(cloud_sync_sqlite_session)
    payload = await service.refresh_projection("fact_shopee_orders_daily")

    assert payload["status"] == "submitted"
    assert payload["source_table_name"] == "fact_shopee_orders_daily"
    assert payload["metadata"]["run_id"] == "run-1"
    assert "api.business_overview_kpi_module" in calls["targets"]
