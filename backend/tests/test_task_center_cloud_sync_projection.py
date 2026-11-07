from datetime import datetime

import asyncio

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.cloud_b_class_auto_sync_worker import CloudBClassAutoSyncWorker
from backend.utils.events import DataIngestedEvent
from modules.core.db import Base, CloudBClassSyncTask, TaskCenterTask


# SQLite 建不了 ``a_class.operating_costs``: 它的 server_default 用了 postgres 专有的
# ``'[]'::jsonb`` 转型表达式, SQLite 解析不了(``unrecognized token: ":"``)。
# 这张表与 task-center 用例无关, 建表时跳过(做法同 test_price_adjust_notification.py)。
_SQLITE_UNSUPPORTED_TABLES = {("a_class", "operating_costs")}


def _sqlite_tables():
    """返回能在 SQLite 上建出来的表(排除 postgres 专有 DDL 的表)。"""
    return [
        table
        for table in Base.metadata.sorted_tables
        if (str(table.schema), table.name) not in _SQLITE_UNSUPPORTED_TABLES
    ]


def _build_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        for schema_name in (
            "core",
            "a_class",
            "b_class",
            "c_class",
            "finance",
            "ops",
            "semantic",
        ):
            conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        Base.metadata.create_all(bind=conn, tables=_sqlite_tables())
    return engine


def _build_session():
    engine = _build_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    return engine, session


def _build_event(source_table_name: str):
    return DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        sub_domain=None,
        granularity="daily",
        source_table_name=source_table_name,
        row_count=10,
    )


def test_cloud_sync_enqueue_writes_task_center_row():
    engine, db = _build_session()
    table_name = "fact_shopee_orders_daily"
    try:
        payload = CloudBClassAutoSyncDispatchService(db).enqueue_or_coalesce(
            _build_event(table_name)
        )
        mirrored = db.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == payload["job_id"])
        ).scalar_one_or_none()

        assert mirrored is not None
        assert mirrored.task_family == "cloud_sync"
        assert mirrored.source_table_name == table_name
    finally:
        db.close()
        engine.dispose()


class _FakeSyncExecutor:
    def sync_table(self, source_table_name: str, batch_size: int = 1000):
        # 签名要与真实执行器一致(``CloudBClassSyncService.sync_table(table_name, batch_size=1000)``),
        # worker 会以 ``batch_size=`` 关键字调用它。
        return {
            "status": "completed",
            "projection_status": "completed",
            "source_table_name": source_table_name,
        }


def test_cloud_sync_worker_updates_task_center_status():
    engine, db = _build_session()
    table_name = "fact_shopee_orders_daily_worker"
    try:
        payload = CloudBClassAutoSyncDispatchService(db).enqueue_or_coalesce(
            _build_event(table_name)
        )
        worker = CloudBClassAutoSyncWorker(db, sync_executor=_FakeSyncExecutor())

        asyncio.run(worker.run_one(worker_id="worker-1"))

        mirrored = db.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == payload["job_id"])
        ).scalar_one()

        assert mirrored.status == "completed"
        assert mirrored.finished_at is not None
    finally:
        db.close()
        engine.dispose()
