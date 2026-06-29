from datetime import date, datetime, timezone

import pytest

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.services import cloud_b_class_sync_service
from modules.core import db as core_db


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_cloud_sync_receive_log_recorder_writes_success_ledger_row():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
    CloudSyncReceiveLog = getattr(core_db, "CloudSyncReceiveLog")
    CloudSyncReceiveLogRecorder = getattr(cloud_b_class_sync_service, "CloudSyncReceiveLogRecorder")
    CloudSyncReceiveLog.__table__.create(bind=engine, checkfirst=True)

    recorder = CloudSyncReceiveLogRecorder(engine, source_environment="collection")

    result = recorder.record_success(
        source_table_name="fact_shopee_orders_monthly",
        source_file_id=2804,
        platform_code="shopee",
        data_domain="orders",
        granularity="monthly",
        checkpoint_scope="b_class",
        source_latest_ingest_timestamp=datetime(2026, 6, 29, 4, 15, tzinfo=timezone.utc),
        written_rows=2,
        rows=[
            {"business_date": date(2026, 6, 22)},
            {"business_date": date(2026, 6, 28)},
        ],
    )

    assert result["status"] == "completed"
    assert result["written_rows"] == 2

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        row = session.execute(select(CloudSyncReceiveLog)).scalar_one()
    finally:
        session.close()

    assert row.receive_id
    assert row.source_environment == "collection"
    assert row.checkpoint_scope == "b_class"
    assert row.source_table_name == "fact_shopee_orders_monthly"
    assert row.source_file_id == 2804
    assert row.platform_code == "shopee"
    assert row.data_domain == "orders"
    assert row.granularity == "monthly"
    assert row.business_date_min == date(2026, 6, 22)
    assert row.business_date_max == date(2026, 6, 28)
    assert _as_utc(row.source_latest_ingest_timestamp) == datetime(2026, 6, 29, 4, 15, tzinfo=timezone.utc)
    assert row.written_rows == 2
    assert row.status == "completed"


def test_receive_log_recorder_prefers_explicit_source_file_id_when_rows_are_cloud_payloads():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
    CloudSyncReceiveLog = getattr(core_db, "CloudSyncReceiveLog")
    CloudSyncReceiveLogRecorder = getattr(cloud_b_class_sync_service, "CloudSyncReceiveLogRecorder")
    CloudSyncReceiveLog.__table__.create(bind=engine, checkfirst=True)

    recorder = CloudSyncReceiveLogRecorder(engine, source_environment="collection")

    result = recorder.record_success(
        source_table_name="fact_shopee_orders_monthly",
        source_file_id=2804,
        platform_code="shopee",
        data_domain="orders",
        granularity="monthly",
        checkpoint_scope="cloud_sync:test",
        source_latest_ingest_timestamp=datetime(2026, 6, 29, 6, 10, tzinfo=timezone.utc),
        written_rows=1,
        rows=[
            {
                "file_id": None,
                "period_end_date": date(2026, 6, 28),
            }
        ],
    )

    assert result["receive_id"].startswith("receive-")

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        row = session.execute(select(CloudSyncReceiveLog)).scalar_one()
    finally:
        session.close()

    assert row.source_file_id == 2804
    assert row.business_date_min == date(2026, 6, 28)
    assert row.business_date_max == date(2026, 6, 28)


def test_cloud_writer_rolls_back_fact_rows_when_receive_log_write_fails():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS b_class")
        conn.execute(
            text(
                """
                CREATE TABLE b_class.fact_shopee_orders_monthly (
                    platform_code TEXT,
                    shop_id TEXT,
                    data_domain TEXT NOT NULL,
                    granularity TEXT NOT NULL,
                    sub_domain TEXT,
                    metric_date DATE,
                    period_start_date DATE,
                    period_end_date DATE,
                    period_start_time TIMESTAMP,
                    period_end_time TIMESTAMP,
                    file_id INTEGER,
                    template_id INTEGER,
                    data_hash TEXT NOT NULL,
                    ingest_timestamp TIMESTAMP,
                    currency_code TEXT,
                    raw_data TEXT NOT NULL,
                    header_columns TEXT,
                    UNIQUE(platform_code, shop_id, data_domain, granularity, data_hash)
                )
                """
            )
        )

    writer = cloud_b_class_sync_service.SQLAlchemyCloudWriter(engine)
    recorder = cloud_b_class_sync_service.CloudSyncReceiveLogRecorder(
        engine,
        source_environment="collection",
    )
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
            "metric_date": None,
            "period_start_date": date(2026, 6, 1),
            "period_end_date": date(2026, 6, 28),
            "period_start_time": None,
            "period_end_time": None,
            "file_id": None,
            "template_id": None,
            "data_hash": "hash-2804",
            "ingest_timestamp": datetime(2026, 6, 29, 4, 15, tzinfo=timezone.utc),
            "currency_code": "MYR",
            "raw_data": {"_cloud_sync_source_file_id": 2804, "_cloud_sync_receive_id": "receive-test"},
            "header_columns": [],
        }
    ]

    with pytest.raises(Exception) as exc_info:
        writer.write_rows_with_receive_log(
            table_name="fact_shopee_orders_monthly",
            rows=rows,
            data_domain="orders",
            receive_log_recorder=recorder,
            receive_log_context={
                "source_table_name": "fact_shopee_orders_monthly",
                "receive_id": "receive-test",
                "source_file_id": 2804,
                "platform_code": "shopee",
                "data_domain": "orders",
                "granularity": "monthly",
                "checkpoint_scope": "b_class",
                "source_latest_ingest_timestamp": datetime(2026, 6, 29, 4, 15, tzinfo=timezone.utc),
                "written_rows": 1,
                "rows": rows,
            },
        )

    assert "cloud_sync_receive_log" in str(exc_info.value)
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM b_class.fact_shopee_orders_monthly")).scalar_one()
    assert count == 0
