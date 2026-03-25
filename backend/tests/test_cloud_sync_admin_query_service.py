from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.cloud_sync_admin_query_service import CloudSyncAdminQueryService
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


@pytest_asyncio.fixture
async def seeded_cloud_sync_query_data(cloud_sync_sqlite_session):
    now = datetime.now(timezone.utc)

    checkpoint = CloudBClassSyncCheckpoint(
        table_schema="cloud_sync:demo",
        table_name="fact_shopee_orders_daily",
        last_source_id=321,
        last_status="completed",
        last_ingest_timestamp=now - timedelta(minutes=10),
    )
    task = CloudBClassSyncTask(
        job_id="job-1",
        dedupe_key="fact_shopee_orders_daily",
        source_table_name="fact_shopee_orders_daily",
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
        trigger_source="auto_ingest",
        status="pending",
        attempt_count=1,
        projection_preset="orders",
        projection_status="pending",
        metadata_json={"trigger_count": 1},
        created_at=now - timedelta(minutes=30),
    )

    cloud_sync_sqlite_session.add_all([checkpoint, task])
    await cloud_sync_sqlite_session.commit()
    return cloud_sync_sqlite_session


@pytest.mark.asyncio
async def test_health_summary_contains_worker_tunnel_cloud_db_queue(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    payload = await service.get_health_summary(
        runtime_health={
            "status": "running",
            "worker_id": "worker-1",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    assert set(payload.keys()) == {"worker", "tunnel", "cloud_db", "queue"}
    assert payload["worker"]["status"] == "running"
    assert payload["queue"]["pending"] == 1


@pytest.mark.asyncio
async def test_table_state_row_contains_checkpoint_and_projection_sections(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    rows = await service.list_table_states()

    assert len(rows) == 1
    row = rows[0]
    assert row["source_table_name"] == "fact_shopee_orders_daily"
    assert row["checkpoint"]["last_source_id"] == 321
    assert row["latest_task"]["job_id"] == "job-1"
    assert row["projection"]["status"] == "pending"
