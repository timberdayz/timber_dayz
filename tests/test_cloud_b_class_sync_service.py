import asyncio
from datetime import datetime, timezone

from backend.services.cloud_b_class_sync_service import (
    CloudRefreshQueueEnqueuer,
    CloudBClassSyncService,
    SQLAlchemyBClassSourceReader,
    SQLAlchemyCloudWriter,
)
from modules.core.db import RefreshQueueTask
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import StaticPool


class FakeCheckpoint:
    def __init__(self, last_ingest_timestamp=None, last_source_id=None):
        self.last_ingest_timestamp = last_ingest_timestamp
        self.last_source_id = last_source_id


class FakeCheckpointService:
    def __init__(self):
        self.checkpoint = FakeCheckpoint()
        self.advanced = []
        self.failures = []
        self.requests = []

    def create_or_get_checkpoint(self, table_name, table_schema="b_class"):
        self.requests.append(("get", table_name, table_schema))
        return self.checkpoint

    def advance_checkpoint(self, table_name, ingest_timestamp, source_id, status, table_schema="b_class"):
        self.advanced.append((table_name, ingest_timestamp, source_id, status, table_schema))
        self.checkpoint.last_ingest_timestamp = ingest_timestamp
        self.checkpoint.last_source_id = source_id

    def mark_failure(self, table_name, message, table_schema="b_class"):
        self.failures.append((table_name, message, table_schema))


class FakeMirrorManager:
    def __init__(self):
        self.ensured = []

    def ensure_cloud_mirror_table(self, table_name, data_domain):
        self.ensured.append((table_name, data_domain))


class FakeProjectionEnqueuer:
    def __init__(self, *, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    def enqueue_after_sync(self, *, source_table_name, data_domain, written_rows, checkpoint_scope):
        self.calls.append(
            {
                "source_table_name": source_table_name,
                "data_domain": data_domain,
                "written_rows": written_rows,
                "checkpoint_scope": checkpoint_scope,
            }
        )
        if self.should_fail:
            raise RuntimeError("queue unavailable")
        return {
            "status": "queued",
            "job_id": "refresh-job-1",
            "targets": ["api.business_overview_kpi_module"],
        }


def test_checkpoint_advances_only_after_successful_write():
    service = CloudBClassSyncService(
        checkpoint_service=FakeCheckpointService(),
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
    )

    assert service._should_advance_checkpoint(write_succeeded=False) is False
    assert service._should_advance_checkpoint(write_succeeded=True) is True


def test_filter_b_class_tables_returns_only_fact_tables():
    service = CloudBClassSyncService(
        checkpoint_service=FakeCheckpointService(),
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
    )

    tables = [
        "fact_shopee_orders_daily",
        "fact_tiktok_services_agent_monthly",
        "dim_platforms",
        "public.misc_table",
    ]

    assert service._filter_b_class_tables(tables) == [
        "fact_shopee_orders_daily",
        "fact_tiktok_services_agent_monthly",
    ]


def test_build_checkpoint_where_clause_uses_timestamp_and_id():
    service = CloudBClassSyncService(
        checkpoint_service=FakeCheckpointService(),
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
    )

    where_sql, params = service._build_checkpoint_where_clause(
        FakeCheckpoint(
            last_ingest_timestamp=datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc),
            last_source_id=123,
        )
    )

    assert "ingest_timestamp > :last_ingest_timestamp" in where_sql
    assert "id > :last_source_id" in where_sql
    assert params["last_source_id"] == 123


def test_sync_table_advances_checkpoint_after_successful_write():
    checkpoint_service = FakeCheckpointService()
    mirror_manager = FakeMirrorManager()

    rows = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
        {"id": 2, "ingest_timestamp": datetime(2026, 3, 24, 0, 5, tzinfo=timezone.utc)},
    ]

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=mirror_manager,
        source_batch_reader=lambda *args, **kwargs: rows,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": len(rows)},
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "completed"
    assert checkpoint_service.advanced == [
        ("fact_shopee_orders_daily", rows[-1]["ingest_timestamp"], rows[-1]["id"], "completed", "b_class")
    ]
    assert mirror_manager.ensured == [("fact_shopee_orders_daily", "orders")]


def test_sync_table_enqueues_cloud_projection_refresh_after_successful_write():
    checkpoint_service = FakeCheckpointService()
    projection_enqueuer = FakeProjectionEnqueuer()
    rows = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
    ]

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: rows,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": len(rows)},
        checkpoint_scope="cloud_sync:target_a",
        projection_enqueuer=projection_enqueuer,
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "completed"
    assert result["projection_status"] == "queued"
    assert result["refresh_queue_job_id"] == "refresh-job-1"
    assert projection_enqueuer.calls == [
        {
            "source_table_name": "fact_shopee_orders_daily",
            "data_domain": "orders",
            "written_rows": 1,
            "checkpoint_scope": "cloud_sync:target_a",
        }
    ]


def test_sync_table_marks_projection_not_required_when_no_refresh_targets_match():
    rows = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
    ]

    service = CloudBClassSyncService(
        checkpoint_service=FakeCheckpointService(),
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: rows,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": len(rows)},
    )

    result = asyncio.run(service.sync_table("fact_shopee_unknown_daily"))

    assert result["status"] == "completed"
    assert result["projection_status"] == "not_required"


def test_sync_table_reports_projection_failure_when_refresh_queue_enqueue_fails():
    rows = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
    ]

    service = CloudBClassSyncService(
        checkpoint_service=FakeCheckpointService(),
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: rows,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": len(rows)},
        projection_enqueuer=FakeProjectionEnqueuer(should_fail=True),
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "completed"
    assert result["projection_status"] == "failed"
    assert result["error_code"] == "projection_runtime_failure"
    assert "queue unavailable" in result["projection_error"]


def test_cloud_refresh_queue_enqueuer_inserts_and_coalesces_target_queue_rows():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        RefreshQueueTask.__table__.create(bind=conn, checkfirst=True)

    enqueuer = CloudRefreshQueueEnqueuer(engine)
    first = enqueuer.enqueue_after_sync(
        source_table_name="fact_shopee_orders_daily",
        data_domain="orders",
        written_rows=5,
        checkpoint_scope="cloud_sync:target_a",
    )
    second = enqueuer.enqueue_after_sync(
        source_table_name="fact_tiktok_orders_daily",
        data_domain="orders",
        written_rows=7,
        checkpoint_scope="cloud_sync:target_a",
    )

    with engine.begin() as conn:
        rows = conn.execute(select(RefreshQueueTask.__table__)).mappings().all()

    assert first["status"] == "queued"
    assert second["status"] == "queued"
    assert second["coalesced"] is True
    assert len(rows) == 1
    assert rows[0]["trigger_type"] == "cloud_sync"
    assert rows[0]["pipeline_name"] == "data_ingested_refresh"
    assert "api.business_overview_kpi_module" in rows[0]["targets_json"]
    assert rows[0]["context_json"]["related_table_names"] == [
        "fact_shopee_orders_daily",
        "fact_tiktok_orders_daily",
    ]


def test_sync_table_does_not_advance_checkpoint_in_dry_run():
    checkpoint_service = FakeCheckpointService()
    mirror_manager = FakeMirrorManager()

    rows = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
    ]

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=mirror_manager,
        source_batch_reader=lambda *args, **kwargs: rows,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": 1, "dry_run": True},
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "completed"
    assert checkpoint_service.advanced == []


def test_sync_table_marks_failure_and_continues_on_single_table_error():
    checkpoint_service = FakeCheckpointService()

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        remote_writer=lambda *args, **kwargs: {"success": True},
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "failed"
    assert checkpoint_service.failures == [("fact_shopee_orders_daily", "boom", "b_class")]


def test_sync_table_uses_isolated_checkpoint_scope_for_target_database():
    checkpoint_service = FakeCheckpointService()

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=FakeMirrorManager(),
        source_batch_reader=lambda *args, **kwargs: [],
        remote_writer=lambda *args, **kwargs: {"success": True},
        checkpoint_scope="cloud_sync:target_a",
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily"))

    assert result["status"] == "completed"
    assert checkpoint_service.requests == [
        ("get", "fact_shopee_orders_daily", "cloud_sync:target_a")
    ]


def test_sync_table_drains_multiple_batches_before_returning_completed():
    checkpoint_service = FakeCheckpointService()
    mirror_manager = FakeMirrorManager()

    batch_one = [
        {"id": 1, "ingest_timestamp": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)},
        {"id": 2, "ingest_timestamp": datetime(2026, 3, 24, 0, 5, tzinfo=timezone.utc)},
    ]
    batch_two = [
        {"id": 3, "ingest_timestamp": datetime(2026, 3, 24, 0, 10, tzinfo=timezone.utc)},
    ]

    def source_batch_reader(*args, **kwargs):
        checkpoint = kwargs["checkpoint"]
        if checkpoint.last_source_id in (None, 0):
            return batch_one
        if checkpoint.last_source_id == 2:
            return batch_two
        return []

    service = CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=mirror_manager,
        source_batch_reader=source_batch_reader,
        remote_writer=lambda *args, **kwargs: {"success": True, "written_rows": len(kwargs["rows"])},
    )

    result = asyncio.run(service.sync_table("fact_shopee_orders_daily", batch_size=2))

    assert result["status"] == "completed"
    assert result["written_rows"] == 3
    assert checkpoint_service.advanced == [
        ("fact_shopee_orders_daily", batch_one[-1]["ingest_timestamp"], batch_one[-1]["id"], "completed", "b_class"),
        ("fact_shopee_orders_daily", batch_two[-1]["ingest_timestamp"], batch_two[-1]["id"], "completed", "b_class"),
    ]
    assert mirror_manager.ensured == [("fact_shopee_orders_daily", "orders")]


def test_source_reader_builds_checkpointed_select_sql():
    reader = SQLAlchemyBClassSourceReader(engine=None)
    where_sql, params = CloudBClassSyncService._build_checkpoint_where_clause(
        FakeCheckpoint(
            last_ingest_timestamp=datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc),
            last_source_id=123,
        )
    )

    sql = reader._build_select_sql("fact_shopee_orders_daily", where_sql)

    assert 'FROM b_class."fact_shopee_orders_daily"' in sql
    assert "ORDER BY ingest_timestamp ASC, id ASC" in sql
    assert params["last_source_id"] == 123


def test_source_reader_fills_missing_columns_with_null_alias():
    reader = SQLAlchemyBClassSourceReader(engine=None)
    sql = reader._build_select_sql(
        "fact_test_platform_orders_daily",
        "",
        available_columns={"id", "platform_code", "shop_id", "data_domain", "granularity", "metric_date", "file_id", "raw_data", "header_columns", "data_hash", "ingest_timestamp", "currency_code"},
    )

    assert "NULL AS period_start_date" in sql
    assert "NULL AS period_end_date" in sql
    assert "NULL AS period_start_time" in sql
    assert "NULL AS period_end_time" in sql


def test_cloud_writer_uses_services_specific_conflict_clause():
    writer = SQLAlchemyCloudWriter(engine=None)
    sql = writer._build_upsert_sql("fact_shopee_services_agent_daily", "services")

    assert 'ON CONFLICT (data_domain, sub_domain, granularity, data_hash)' in sql


def test_cloud_writer_uses_non_services_conflict_clause():
    writer = SQLAlchemyCloudWriter(engine=None)
    sql = writer._build_upsert_sql("fact_shopee_orders_daily", "orders")

    assert 'ON CONFLICT (platform_code, shop_id, data_domain, granularity, data_hash)' in sql


def test_cloud_writer_serializes_json_fields_before_insert():
    writer = SQLAlchemyCloudWriter(engine=None)
    rows = writer._prepare_rows_for_insert(
        [
            {
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "data_domain": "orders",
                "granularity": "daily",
                "sub_domain": None,
                "metric_date": None,
                "period_start_date": None,
                "period_end_date": None,
                "period_start_time": None,
                "period_end_time": None,
                "file_id": 1,
                "template_id": None,
                "data_hash": "hash-1",
                "ingest_timestamp": None,
                "currency_code": "USD",
                "raw_data": {"订单号": "A-1"},
                "header_columns": ["订单号"],
            }
        ]
    )

    assert isinstance(rows[0]["raw_data"], str)
    assert isinstance(rows[0]["header_columns"], str)
