from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.core.db import CloudBClassSyncTask


class CloudBClassAutoSyncDispatchService:
    """Persist or coalesce automatic cloud-sync tasks."""

    RUNNABLE_STATUSES = ("pending", "running", "retry_waiting")

    def __init__(self, db: Session):
        self.db = db

    def enqueue_or_coalesce(self, event) -> dict:
        dedupe_key = self._build_dedupe_key(event)
        existing = self._find_existing_task(dedupe_key)

        if existing:
            metadata = dict(existing.metadata_json or {})
            metadata["trigger_count"] = int(metadata.get("trigger_count", 1)) + 1
            metadata["latest_trigger_at"] = event.timestamp
            existing.metadata_json = metadata
            if event.file_id is not None:
                existing.source_file_id = event.file_id
            self.db.commit()
            self.db.refresh(existing)
            return {
                "job_id": existing.job_id,
                "task_id": existing.id,
                "status": existing.status,
                "metadata": existing.metadata_json or {},
                "coalesced": True,
            }

        task = CloudBClassSyncTask(
            job_id=f"cloud-sync-{uuid4().hex}",
            dedupe_key=dedupe_key,
            source_table_name=event.source_table_name,
            platform_code=event.platform_code,
            data_domain=event.data_domain,
            sub_domain=event.sub_domain,
            granularity=event.granularity,
            trigger_source="auto_ingest",
            source_file_id=event.file_id,
            status="pending",
            projection_preset=self._resolve_projection_preset(event),
            metadata_json={
                "trigger_count": 1,
                "latest_trigger_at": event.timestamp,
            },
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return {
            "job_id": task.job_id,
            "task_id": task.id,
            "status": task.status,
            "metadata": task.metadata_json or {},
            "coalesced": False,
        }

    def _find_existing_task(self, dedupe_key: str) -> CloudBClassSyncTask | None:
        stmt = (
            select(CloudBClassSyncTask)
            .where(
                CloudBClassSyncTask.dedupe_key == dedupe_key,
                CloudBClassSyncTask.status.in_(self.RUNNABLE_STATUSES),
            )
            .order_by(CloudBClassSyncTask.id.desc())
        )
        return self.db.execute(stmt).scalars().first()

    @staticmethod
    def _build_dedupe_key(event) -> str:
        return event.source_table_name

    @staticmethod
    def _resolve_projection_preset(event) -> str | None:
        if event.projection_preset:
            return event.projection_preset
        if event.data_domain in {"orders", "products", "inventory", "analytics", "services"}:
            return event.data_domain
        return None
