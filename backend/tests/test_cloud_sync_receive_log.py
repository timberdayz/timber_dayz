from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
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
