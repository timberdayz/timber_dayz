from __future__ import annotations

import inspect

from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.cloud_sync_admin import CloudSyncCommandResponse
from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.cloud_b_class_auto_sync_factory import (
    _build_checkpoint_scope_key,
    build_cloud_sync_service_from_env,
)
from backend.services.event_listeners import determine_pipeline_targets_for_data_ingested
from backend.services.data_pipeline.refresh_runner import execute_refresh_plan
from backend.services.cloud_b_class_sync_utils import validate_b_class_table_name
from backend.utils.events import DataIngestedEvent
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask


class CloudSyncAdminCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

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
        service = build_cloud_sync_service_from_env(dry_run=True)
        try:
            result = await self._maybe_await(service.sync_table(source_table_name))
        finally:
            if hasattr(service, "close"):
                service.close()

        return CloudSyncCommandResponse(
            status=result.get("status", "completed"),
            source_table_name=source_table_name,
            detail="dry_run",
            metadata=result,
        ).model_dump()

    async def repair_checkpoint(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)
        stmt = select(CloudBClassSyncCheckpoint).where(
            CloudBClassSyncCheckpoint.table_name == source_table_name,
            or_(
                CloudBClassSyncCheckpoint.table_schema.like("cloud_sync:%"),
                CloudBClassSyncCheckpoint.table_schema == "cloud_sync:local",
            ),
        )
        checkpoints = (await self.db.execute(stmt)).scalars().all()

        if not checkpoints:
            checkpoint = CloudBClassSyncCheckpoint(
                table_schema=_build_checkpoint_scope_key(None, dry_run=False),
                table_name=source_table_name,
                last_status="pending",
            )
            self.db.add(checkpoint)
            checkpoints = [checkpoint]

        for checkpoint in checkpoints:
            checkpoint.last_ingest_timestamp = None
            checkpoint.last_source_id = None
            checkpoint.last_status = "pending"
            checkpoint.last_error = None

        await self.db.commit()

        return CloudSyncCommandResponse(
            status="repaired",
            source_table_name=source_table_name,
            detail="checkpoint_reset",
            metadata={"checkpoint_count": len(checkpoints)},
        ).model_dump()

    async def refresh_projection(self, source_table_name: str) -> dict:
        source_table_name = validate_b_class_table_name(source_table_name)
        event = DataIngestedEvent(
            file_id=None,
            platform_code=None,
            data_domain=self._infer_data_domain(source_table_name),
            sub_domain=None,
            granularity=None,
            source_table_name=source_table_name,
            row_count=0,
        )
        targets = determine_pipeline_targets_for_data_ingested(event)
        if not targets:
            return CloudSyncCommandResponse(
                status="skipped",
                source_table_name=source_table_name,
                detail="no_projection_targets",
                metadata={"target_count": 0},
            ).model_dump()

        run_id = await execute_refresh_plan(
            self.db,
            targets=targets,
            pipeline_name="cloud_sync_admin_projection_refresh",
            trigger_source="cloud_sync_admin",
            context={"source_table_name": source_table_name, "data_domain": event.data_domain},
            continue_on_error=True,
            max_attempts=1,
            retry_backoff_seconds=0.0,
        )
        await self.db.commit()

        return CloudSyncCommandResponse(
            status="submitted",
            source_table_name=source_table_name,
            detail="projection_refresh",
            metadata={"run_id": run_id, "target_count": len(targets), "targets": targets},
        ).model_dump()

    async def _get_task(self, job_id: str) -> CloudBClassSyncTask | None:
        stmt = select(CloudBClassSyncTask).where(CloudBClassSyncTask.job_id == job_id)
        return (await self.db.execute(stmt)).scalars().one_or_none()

    @staticmethod
    def _infer_data_domain(source_table_name: str) -> str:
        parts = source_table_name.split("_")
        if len(parts) < 4 or parts[0] != "fact":
            raise ValueError(f"Unsupported B-class table name: {source_table_name}")
        return parts[2]
