import asyncio
from datetime import datetime, timezone

from backend.services.cloud_b_class_sync_service import (
    CloudBClassSyncService,
    SQLAlchemyBClassSourceReader,
    SQLAlchemyCloudWriter,
)


class FakeCheckpoint:
    def __init__(self, last_ingest_timestamp=None, last_source_id=None):
        self.last_ingest_timestamp = last_ingest_timestamp
        self.last_source_id = last_source_id


class FakeCheckpointService:
    def __init__(self):
        self.checkpoint = FakeCheckpoint()
        self.advanced = []
        self.failures = []

    def create_or_get_checkpoint(self, table_name):
        return self.checkpoint

    def advance_checkpoint(self, table_name, ingest_timestamp, source_id, status):
        self.advanced.append((table_name, ingest_timestamp, source_id, status))

    def mark_failure(self, table_name, message):
        self.failures.append((table_name, message))


class FakeMirrorManager:
    def __init__(self):
        self.ensured = []

    def ensure_cloud_mirror_table(self, table_name, data_domain):
        self.ensured.append((table_name, data_domain))


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
        ("fact_shopee_orders_daily", rows[-1]["ingest_timestamp"], rows[-1]["id"], "completed")
    ]
    assert mirror_manager.ensured == [("fact_shopee_orders_daily", "orders")]


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
    assert checkpoint_service.failures == [("fact_shopee_orders_daily", "boom")]


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
