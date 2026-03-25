from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.cloud_sync_admin import CloudSyncCommandResponse
from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.cloud_b_class_sync_utils import validate_b_class_table_name
from backend.utils.events import DataIngestedEvent
from modules.core.db import CloudBClassSyncTask


class CloudSyncAdminCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def trigger_sync(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)

        def _enqueue(sync_session):
            service = CloudBClassAutoSyncDispatchService(sync_session)
            return service.enqueue_or_coalesce(
                DataIngestedEvent(
                    file_id=None,
                    platform_code=None,
                    data_domain=None,
                    sub_domain=None,
                    granularity=None,
                    source_table_name=source_table_name,
                    row_count=0,
                )
            )

        payload = await self.db.run_sync(_enqueue)
        return CloudSyncCommandResponse(
            job_id=payload.get("job_id"),
            status=payload.get("status", "pending"),
            source_table_name=source_table_name,
            metadata=payload.get("metadata", {}),
        ).model_dump()

    async def retry_task(self, job_id: str) -> dict:
        task = await self._get_task(job_id)
        if task is None:
            return CloudSyncCommandResponse(job_id=job_id, status="not_found").model_dump()

        task.status = "pending"
        task.next_retry_at = None
        await self.db.commit()
        await self.db.refresh(task)
        return CloudSyncCommandResponse(
            job_id=task.job_id,
            status=task.status,
            source_table_name=task.source_table_name,
        ).model_dump()

    async def cancel_task(self, job_id: str) -> dict:
        task = await self._get_task(job_id)
        if task is None:
            return CloudSyncCommandResponse(job_id=job_id, status="not_found").model_dump()

        task.status = "cancelled"
        task.next_retry_at = None
        task.lease_expires_at = None
        await self.db.commit()
        await self.db.refresh(task)
        return CloudSyncCommandResponse(
            job_id=task.job_id,
            status=task.status,
            source_table_name=task.source_table_name,
        ).model_dump()

    async def dry_run_table(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)
        return CloudSyncCommandResponse(
            status="accepted",
            source_table_name=source_table_name,
            detail="dry_run_not_implemented_yet",
        ).model_dump()

    async def repair_checkpoint(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)
        return CloudSyncCommandResponse(
            status="accepted",
            source_table_name=source_table_name,
            detail="repair_checkpoint_not_implemented_yet",
        ).model_dump()

    async def refresh_projection(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)
        return CloudSyncCommandResponse(
            status="accepted",
            source_table_name=source_table_name,
            detail="refresh_projection_not_implemented_yet",
        ).model_dump()

    async def _get_task(self, job_id: str) -> CloudBClassSyncTask | None:
        stmt = select(CloudBClassSyncTask).where(CloudBClassSyncTask.job_id == job_id)
        return (await self.db.execute(stmt)).scalars().one_or_none()
