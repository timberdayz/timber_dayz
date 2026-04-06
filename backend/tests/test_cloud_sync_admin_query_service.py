from datetime import datetime, timedelta, timezone
import socket

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.cloud_sync_admin_query_service import CloudSyncAdminQueryService
from modules.core.db import Base
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask, SystemConfig


@pytest_asyncio.fixture
async def cloud_sync_sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.execute(text("CREATE TABLE core.dim_users (user_id INTEGER PRIMARY KEY)"))
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                CloudBClassSyncCheckpoint.__table__,
                CloudBClassSyncTask.__table__,
                SystemConfig.__table__,
            ],
        )

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


@pytest.mark.asyncio
async def test_query_service_redacts_credentials_in_errors(cloud_sync_sqlite_session):
    task = CloudBClassSyncTask(
        job_id="job-sensitive",
        dedupe_key="fact_sensitive",
        source_table_name="fact_sensitive",
        status="failed",
        last_error="postgresql://erp_user:super-secret@db.example.com/xihong_erp failed",
    )
    cloud_sync_sqlite_session.add(task)
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    rows = await service.list_tasks()

    assert rows[0]["last_error"] is not None
    assert "super-secret" not in rows[0]["last_error"]
    assert "***" in rows[0]["last_error"]


@pytest.mark.asyncio
async def test_health_summary_probes_local_forwarded_cloud_db(monkeypatch, seeded_cloud_sync_query_data):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        f"postgresql://erp_user:secret-pass@127.0.0.1:{port}/xihong_erp",
    )

    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)
    payload = await service.get_health_summary()

    listener.close()

    assert payload["cloud_db"]["status"] == "reachable"
    assert payload["tunnel"]["status"] == "healthy"
    assert payload["cloud_db"]["error"] is None


@pytest.mark.asyncio
async def test_health_summary_redacts_cloud_db_probe_error(monkeypatch, seeded_cloud_sync_query_data):
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        "postgresql://erp_user:secret-pass@127.0.0.1:1/xihong_erp",
    )

    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)
    payload = await service.get_health_summary()

    assert payload["cloud_db"]["status"] == "unreachable"
    assert payload["cloud_db"]["error"] is not None
    assert "secret-pass" not in payload["cloud_db"]["error"]


@pytest.mark.asyncio
async def test_overview_summary_includes_catch_up_status_and_exception_count(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    payload = await service.get_overview_summary(
        runtime_health={
            "status": "running",
            "worker_id": "worker-1",
        }
    )

    assert payload["worker_status"] == "running"
    assert payload["catch_up_status"] in {"up_to_date", "catching_up", "backlog", "degraded"}
    assert "exception_task_count" in payload


@pytest.mark.asyncio
async def test_runtime_summary_includes_is_running_and_progress_fields(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    payload = await service.get_runtime_summary(
        runtime_health={
            "status": "running",
            "worker_id": "worker-1",
        }
    )

    assert payload["worker_status"] == "running"
    assert "is_running" in payload
    assert "active_task_count" in payload


@pytest.mark.asyncio
async def test_history_summary_returns_recent_sync_rows(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    rows = await service.list_history()

    assert len(rows) == 1
    assert rows[0]["job_id"] == "job-1"
    assert rows[0]["result_status"] == "pending"


@pytest.mark.asyncio
async def test_settings_summary_returns_auto_sync_state(seeded_cloud_sync_query_data):
    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)

    payload = await service.get_settings()

    assert "auto_sync_enabled" in payload
    assert "pause_mode" in payload


@pytest.mark.asyncio
async def test_settings_summary_reads_persisted_auto_sync_flag(cloud_sync_sqlite_session):
    cloud_sync_sqlite_session.add(
        SystemConfig(
            config_key="cloud_sync_auto_sync_enabled",
            config_value="false",
        )
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    payload = await service.get_settings()

    assert payload["auto_sync_enabled"] is False
