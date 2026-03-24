from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.core.db import CloudBClassSyncCheckpoint


class CloudBClassSyncCheckpointService:
    """Manage per-table checkpoints for B-class cloud sync."""

    def __init__(self, db: Session):
        self.db = db

    def get_checkpoint(self, table_name: str, table_schema: str = "b_class") -> CloudBClassSyncCheckpoint | None:
        stmt = select(CloudBClassSyncCheckpoint).where(
            CloudBClassSyncCheckpoint.table_schema == table_schema,
            CloudBClassSyncCheckpoint.table_name == table_name,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create_or_get_checkpoint(
        self, table_name: str, table_schema: str = "b_class"
    ) -> CloudBClassSyncCheckpoint:
        checkpoint = self.get_checkpoint(table_name=table_name, table_schema=table_schema)
        if checkpoint:
            return checkpoint

        checkpoint = CloudBClassSyncCheckpoint(
            table_schema=table_schema,
            table_name=table_name,
            last_status="pending",
        )
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def advance_checkpoint(
        self,
        table_name: str,
        ingest_timestamp,
        source_id: int,
        status: str,
        table_schema: str = "b_class",
    ) -> CloudBClassSyncCheckpoint:
        checkpoint = self.create_or_get_checkpoint(table_name=table_name, table_schema=table_schema)
        checkpoint.last_ingest_timestamp = ingest_timestamp
        checkpoint.last_source_id = source_id
        checkpoint.last_status = status
        checkpoint.last_error = None
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def mark_failure(
        self, table_name: str, message: str, table_schema: str = "b_class"
    ) -> CloudBClassSyncCheckpoint:
        checkpoint = self.create_or_get_checkpoint(table_name=table_name, table_schema=table_schema)
        checkpoint.last_status = "failed"
        checkpoint.last_error = message
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint
