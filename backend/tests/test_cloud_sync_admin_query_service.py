from datetime import datetime, timedelta, timezone
import socket
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.cloud_b_class_auto_sync_factory import _build_checkpoint_scope_key
from backend.services.cloud_sync_admin_query_service import CloudSyncAdminQueryService
from modules.core.db import Base
from modules.core.db import (
    CatalogFile,
    CloudBClassSyncCheckpoint,
    CloudBClassSyncTask,
    CloudSyncReceiveLog,
    RefreshQueueTask,
    SystemConfig,
    TaskCenterTask,
)


@pytest_asyncio.fixture
async def cloud_sync_sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance", "ops"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.execute(text("CREATE TABLE core.dim_users (user_id INTEGER PRIMARY KEY)"))
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                CatalogFile.__table__,
                CloudBClassSyncCheckpoint.__table__,
                CloudBClassSyncTask.__table__,
                CloudSyncReceiveLog.__table__,
                RefreshQueueTask.__table__,
                SystemConfig.__table__,
                TaskCenterTask.__table__,
            ],
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_cloud_sync_query_data(cloud_sync_sqlite_session):
    now = datetime.now(timezone.utc)
    current_scope = _build_checkpoint_scope_key(
        os.getenv("CLOUD_DATABASE_URL"),
        dry_run=False,
    )

    checkpoint = CloudBClassSyncCheckpoint(
        table_schema=current_scope,
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
    assert payload["queue"]["stale_running"] == 0


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
async def test_table_state_row_includes_lifecycle_and_receive_log(cloud_sync_sqlite_session):
    now = datetime.now(timezone.utc)
    cloud_sync_sqlite_session.add_all(
        [
            CatalogFile(
                id=2804,
                file_path="data/raw/2026/shopee_orders_monthly.xls",
                file_name="shopee_orders_monthly.xls",
                platform_code="shopee",
                account="acc-1",
                data_domain="orders",
                granularity="monthly",
                status="ingested",
                file_metadata={"collection_task_id": "collection-1"},
            ),
            TaskCenterTask(
                task_id="single_file_2804_abc12345",
                task_family="data_sync",
                task_type="single_file",
                status="completed",
                source_file_id=2804,
                details_json={"ingest": {"source": "post_collection"}},
            ),
            CloudBClassSyncTask(
                job_id="job-lifecycle",
                dedupe_key="fact_shopee_orders_monthly",
                source_table_name="fact_shopee_orders_monthly",
                platform_code="shopee",
                data_domain="orders",
                granularity="monthly",
                source_file_id=2804,
                status="running",
                projection_status="queued",
                metadata_json={"checkpoint_scope": "b_class"},
                created_at=now - timedelta(minutes=5),
            ),
            CloudSyncReceiveLog(
                receive_id="receive-1",
                source_environment="collection",
                checkpoint_scope="b_class",
                source_table_name="fact_shopee_orders_monthly",
                source_file_id=2804,
                platform_code="shopee",
                data_domain="orders",
                granularity="monthly",
                business_date_min=datetime(2026, 6, 22, tzinfo=timezone.utc).date(),
                business_date_max=datetime(2026, 6, 28, tzinfo=timezone.utc).date(),
                source_latest_ingest_timestamp=now - timedelta(minutes=2),
                written_rows=77,
                status="completed",
            ),
            RefreshQueueTask(
                job_id="refresh-1",
                trigger_type="cloud_sync",
                pipeline_name="data_ingested_refresh",
                dedupe_key="dedupe-1",
                targets_json=["ops.pipeline_run_log"],
                context_json={"source_table_name": "fact_shopee_orders_monthly"},
                status="running",
            ),
        ]
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    rows = await service.list_table_states()
    row = next(item for item in rows if item["source_table_name"] == "fact_shopee_orders_monthly")

    assert row["lifecycle"]["collection_status"] == "completed"
    assert row["lifecycle"]["local_ingest_status"] == "completed"
    assert row["lifecycle"]["cloud_sync_status"] == "running"
    assert row["lifecycle"]["cloud_refresh_status"] == "running"
    assert row["receive_log"]["last_receive_at"] is not None
    assert row["receive_log"]["last_written_rows"] == 77


@pytest.mark.asyncio
async def test_overview_summary_includes_pipeline_lifecycle_counts(cloud_sync_sqlite_session):
    now = datetime.now(timezone.utc)
    cloud_sync_sqlite_session.add_all(
        [
            CatalogFile(
                id=2803,
                file_path="data/raw/2026/tiktok_orders_monthly.xls",
                file_name="tiktok_orders_monthly.xls",
                platform_code="tiktok",
                account="acc-1",
                data_domain="orders",
                granularity="monthly",
                status="pending",
                first_seen_at=now - timedelta(minutes=45),
            ),
            RefreshQueueTask(
                job_id="refresh-failed",
                trigger_type="cloud_sync",
                pipeline_name="data_ingested_refresh",
                dedupe_key="dedupe-refresh-failed",
                targets_json=["ops.pipeline_run_log"],
                context_json={"source_table_name": "fact_shopee_orders_monthly"},
                status="failed",
            ),
        ]
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    payload = await service.get_overview_summary(runtime_health={"status": "running"})

    assert payload["pending_catalog_file_count"] == 1
    assert payload["overdue_pending_catalog_file_count"] == 1
    assert payload["refresh_failed_task_count"] == 1
    assert payload["last_receive_at"] is None


@pytest.mark.asyncio
async def test_table_state_rows_only_include_current_scope_checkpoint(
    monkeypatch,
    cloud_sync_sqlite_session,
):
    current_cloud_url = "postgresql://erp_user:secret-pass@127.0.0.1:15433/xihong_erp"
    other_cloud_url = "postgresql://erp_user:secret-pass@127.0.0.1:15434/xihong_erp"
    monkeypatch.setenv("CLOUD_DATABASE_URL", current_cloud_url)
    current_scope = _build_checkpoint_scope_key(current_cloud_url, dry_run=False)
    other_scope = _build_checkpoint_scope_key(other_cloud_url, dry_run=False)
    now = datetime.now(timezone.utc)
    cloud_sync_sqlite_session.add_all(
        [
            CloudBClassSyncCheckpoint(
                table_schema=other_scope,
                table_name="fact_shopee_orders_daily",
                last_source_id=999,
                last_status="completed",
                last_ingest_timestamp=now - timedelta(minutes=5),
            ),
            CloudBClassSyncCheckpoint(
                table_schema=current_scope,
                table_name="fact_shopee_orders_daily",
                last_source_id=321,
                last_status="completed",
                last_ingest_timestamp=now - timedelta(minutes=10),
            ),
            CloudBClassSyncTask(
                job_id="job-scope-current",
                dedupe_key="fact_shopee_orders_daily",
                source_table_name="fact_shopee_orders_daily",
                status="pending",
                metadata_json={"checkpoint_scope": current_scope},
                created_at=now - timedelta(minutes=1),
            ),
            CloudBClassSyncTask(
                job_id="job-scope-other",
                dedupe_key="fact_shopee_orders_daily-other",
                source_table_name="fact_shopee_orders_daily",
                status="failed",
                metadata_json={"checkpoint_scope": other_scope},
                created_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    rows = await service.list_table_states()

    assert len(rows) == 1
    row = rows[0]
    assert row["checkpoint"]["table_schema"] == current_scope
    assert row["checkpoint"]["last_source_id"] == 321
    assert row["latest_task"]["job_id"] == "job-scope-current"


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
async def test_health_summary_reports_not_configured_when_worker_prereqs_missing(
    monkeypatch,
    seeded_cloud_sync_query_data,
):
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "true")
    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DEPLOYMENT_ROLE", "collector")
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)

    service = CloudSyncAdminQueryService(seeded_cloud_sync_query_data)
    payload = await service.get_health_summary(runtime_health=None)

    assert payload["worker"]["status"] == "not_configured"


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
    assert "last_runtime_heartbeat_at" in payload
    assert "task_heartbeat_at" in payload
    assert "task_lease_expired" in payload


@pytest.mark.asyncio
async def test_query_service_marks_stale_running_as_degraded(monkeypatch, cloud_sync_sqlite_session):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        "postgresql://erp_user:secret-pass@127.0.0.1:15433/xihong_erp",
    )
    current_scope = _build_checkpoint_scope_key(
        "postgresql://erp_user:secret-pass@127.0.0.1:15433/xihong_erp",
        dry_run=False,
    )
    cloud_sync_sqlite_session.add(
        CloudBClassSyncTask(
            job_id="job-stale",
            dedupe_key="fact_stale",
            source_table_name="fact_stale",
            status="running",
            claimed_by="worker-1",
            lease_expires_at=now - timedelta(minutes=2),
            heartbeat_at=now - timedelta(minutes=3),
            metadata_json={"checkpoint_scope": current_scope},
            created_at=now - timedelta(minutes=10),
        )
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    health = await service.get_health_summary(
        runtime_health={"status": "running", "worker_id": "worker-1"}
    )
    overview = await service.get_overview_summary(
        runtime_health={"status": "running", "worker_id": "worker-1"}
    )
    runtime = await service.get_runtime_summary(
        runtime_health={"status": "running", "worker_id": "worker-1"}
    )

    assert health["queue"]["stale_running"] == 1
    assert overview["catch_up_status"] == "degraded"
    assert overview["exception_task_count"] == 1
    assert runtime["active_task_count"] == 0
    assert runtime["is_running"] is False
    assert runtime["worker_status"] == "degraded"


@pytest.mark.asyncio
async def test_query_service_excludes_legacy_scope_stale_from_current_overview(
    monkeypatch,
    cloud_sync_sqlite_session,
):
    now = datetime.now(timezone.utc)
    current_cloud_url = "postgresql://erp_user:secret-pass@127.0.0.1:15433/xihong_erp"
    other_cloud_url = "postgresql://erp_user:secret-pass@127.0.0.1:15434/xihong_erp"
    monkeypatch.setenv("CLOUD_DATABASE_URL", current_cloud_url)
    current_scope = _build_checkpoint_scope_key(current_cloud_url, dry_run=False)
    other_scope = _build_checkpoint_scope_key(other_cloud_url, dry_run=False)

    cloud_sync_sqlite_session.add_all(
        [
            CloudBClassSyncTask(
                job_id="job-current-pending",
                dedupe_key="fact_current",
                source_table_name="fact_current",
                status="pending",
                metadata_json={"checkpoint_scope": current_scope},
                created_at=now - timedelta(minutes=1),
            ),
            CloudBClassSyncTask(
                job_id="job-legacy-stale",
                dedupe_key="fact_legacy",
                source_table_name="fact_legacy",
                status="running",
                claimed_by="worker-legacy",
                lease_expires_at=now - timedelta(minutes=3),
                heartbeat_at=now - timedelta(minutes=4),
                last_error="legacy-scope-error",
                metadata_json={"checkpoint_scope": other_scope},
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    health = await service.get_health_summary(runtime_health={"status": "running", "worker_id": "worker-1"})
    overview = await service.get_overview_summary(runtime_health={"status": "running", "worker_id": "worker-1"})
    runtime = await service.get_runtime_summary(runtime_health={"status": "running", "worker_id": "worker-1"})

    assert health["queue"]["pending"] == 1
    assert health["queue"]["stale_running"] == 0
    assert overview["exception_task_count"] == 0
    assert overview["failed_task_count"] == 0
    assert overview["stale_running_task_count"] == 0
    assert overview["latest_error"] is None
    assert overview["catch_up_status"] == "backlog"
    assert overview["legacy_scope_exception_count"] == 1
    assert overview["current_checkpoint_scope"] == current_scope
    assert runtime["stale_running_count"] == 0
    assert runtime["error_summary"] is None
    assert runtime["legacy_scope_stale_count"] == 1


@pytest.mark.asyncio
async def test_runtime_summary_exposes_task_heartbeat_and_runtime_heartbeat(
    monkeypatch,
    cloud_sync_sqlite_session,
):
    now = datetime.now(timezone.utc)
    current_cloud_url = "postgresql://erp_user:secret-pass@127.0.0.1:15433/xihong_erp"
    monkeypatch.setenv("CLOUD_DATABASE_URL", current_cloud_url)
    current_scope = _build_checkpoint_scope_key(current_cloud_url, dry_run=False)

    cloud_sync_sqlite_session.add(
        CloudBClassSyncTask(
            job_id="job-runtime-heartbeat",
            dedupe_key="fact_runtime_heartbeat",
            source_table_name="fact_runtime_heartbeat",
            status="running",
            claimed_by="worker-1",
            lease_expires_at=now + timedelta(minutes=2),
            heartbeat_at=now - timedelta(seconds=15),
            last_attempt_started_at=now - timedelta(minutes=1),
            metadata_json={"checkpoint_scope": current_scope},
            created_at=now - timedelta(minutes=2),
        )
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    runtime = await service.get_runtime_summary(
        runtime_health={
            "status": "running",
            "worker_id": "worker-1",
            "last_heartbeat_at": now.isoformat(),
            "last_runtime_heartbeat_at": (now - timedelta(seconds=2)).isoformat(),
            "last_recovered_count": 0,
        }
    )

    assert runtime["worker_status"] == "running"
    assert runtime["task_heartbeat_at"] is not None
    assert runtime["task_lease_expires_at"] is not None
    assert runtime["last_runtime_heartbeat_at"] is not None
    assert runtime["current_task_run_seconds"] is not None
    assert runtime["seconds_since_task_heartbeat"] is not None
    assert runtime["task_lease_expired"] is False


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


@pytest.mark.asyncio
async def test_empty_state_query_service_returns_safe_defaults(cloud_sync_sqlite_session):
    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)

    overview = await service.get_overview_summary()
    runtime = await service.get_runtime_summary()
    history = await service.list_history()
    tables = await service.list_table_states()
    events = await service.list_events()

    assert overview["exception_task_count"] == 0
    assert overview["last_success_at"] is None
    assert overview["catch_up_status"] == "up_to_date"
    assert runtime["is_running"] is False
    assert history == []
    assert tables == []
    assert events == []


@pytest.mark.asyncio
async def test_table_state_rows_only_include_current_cloud_scope(
    monkeypatch,
    cloud_sync_sqlite_session,
):
    current_cloud_url = "postgresql://erp_user:erp_pass_2025@127.0.0.1:15433/xihong_erp"
    other_cloud_url = "postgresql://erp_user:erp_pass_2025@127.0.0.1:15434/xihong_erp"
    monkeypatch.setenv("CLOUD_DATABASE_URL", current_cloud_url)
    current_scope = _build_checkpoint_scope_key(current_cloud_url, dry_run=False)
    other_scope = _build_checkpoint_scope_key(other_cloud_url, dry_run=False)

    cloud_sync_sqlite_session.add_all(
        [
            CloudBClassSyncCheckpoint(
                table_schema=current_scope,
                table_name="fact_scope_sensitive",
                last_source_id=11,
                last_status="completed",
                last_ingest_timestamp=datetime.now(timezone.utc),
            ),
            CloudBClassSyncCheckpoint(
                table_schema=other_scope,
                table_name="fact_scope_sensitive",
                last_source_id=22,
                last_status="failed",
                last_error="wrong-scope",
                last_ingest_timestamp=datetime.now(timezone.utc),
            ),
            CloudBClassSyncTask(
                job_id="job-current",
                dedupe_key="fact_scope_sensitive",
                source_table_name="fact_scope_sensitive",
                status="completed",
            ),
        ]
    )
    await cloud_sync_sqlite_session.commit()

    service = CloudSyncAdminQueryService(cloud_sync_sqlite_session)
    rows = await service.list_table_states()

    row = next(item for item in rows if item["source_table_name"] == "fact_scope_sensitive")
    assert row["checkpoint"]["table_schema"] == current_scope
    assert row["checkpoint"]["last_source_id"] == 11
    assert row["checkpoint"]["last_status"] == "completed"
