from __future__ import annotations

import inspect
import os
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy import or_
from sqlalchemy import inspect as sa_inspect
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
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask, SystemConfig


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

    async def sync_now(self) -> dict:
        checked_tables = await self._list_local_b_class_tables()
        enqueued_count = 0
        skipped_count = 0

        for table_name in checked_tables:
            if not await self._table_needs_catch_up(table_name):
                skipped_count += 1
                continue
            await self.trigger_sync(table_name)
            enqueued_count += 1

        return CloudSyncCommandResponse(
            status="submitted",
            detail="catch_up",
            metadata={
                "checked_table_count": len(checked_tables),
                "enqueued_table_count": enqueued_count,
                "skipped_up_to_date_count": skipped_count,
            },
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

    async def retry_failed(self) -> dict:
        stmt = select(CloudBClassSyncTask).where(
            CloudBClassSyncTask.status.in_(["failed", "partial_success"])
        )
        tasks = (await self.db.execute(stmt)).scalars().all()

        for task in tasks:
            task.status = "pending"
            task.next_retry_at = None

        await self.db.commit()

        return CloudSyncCommandResponse(
            status="submitted",
            detail="retry_failed",
            metadata={"retried_count": len(tasks)},
        ).model_dump()

    async def update_settings(self, enabled: bool) -> dict:
        os.environ["CLOUD_SYNC_AUTO_SYNC_ENABLED"] = "true" if enabled else "false"
        stmt = select(SystemConfig).where(SystemConfig.config_key == "cloud_sync_auto_sync_enabled")
        record = (await self.db.execute(stmt)).scalars().one_or_none()
        value = "true" if enabled else "false"
        if record is None:
            record = SystemConfig(
                config_key="cloud_sync_auto_sync_enabled",
                config_value=value,
                description="cloud sync auto sync switch",
            )
            self.db.add(record)
        else:
            record.config_value = value
        await self.db.commit()
        return CloudSyncCommandResponse(
            status="updated",
            detail="settings",
            metadata={
                "auto_sync_enabled": enabled,
                "pause_mode": "buffer_backlog",
            },
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

    async def _list_local_b_class_tables(self) -> list[str]:
        def _inspect_tables(sync_session):
            bind = sync_session.get_bind()
            if bind is None:
                return []
            inspector = sa_inspect(bind)
            return sorted(
                table_name
                for table_name in inspector.get_table_names(schema="b_class")
                if table_name.startswith("fact_")
            )

        return await self.db.run_sync(_inspect_tables)

    async def _table_needs_catch_up(self, table_name: str) -> bool:
        checkpoint_stmt = select(CloudBClassSyncCheckpoint).where(
            CloudBClassSyncCheckpoint.table_name == table_name,
            or_(
                CloudBClassSyncCheckpoint.table_schema.like("cloud_sync:%"),
                CloudBClassSyncCheckpoint.table_schema == "cloud_sync:local",
            ),
        )
        checkpoint = (await self.db.execute(checkpoint_stmt)).scalars().first()
        if checkpoint is None or checkpoint.last_ingest_timestamp is None:
            return True

        def _latest_high_watermark(sync_session):
            sql = text(
                f"""
                SELECT id, ingest_timestamp
                FROM b_class."{table_name}"
                ORDER BY ingest_timestamp DESC, id DESC
                LIMIT 1
                """
            )
            row = sync_session.execute(sql).mappings().first()
            return dict(row) if row else None

        latest_row = await self.db.run_sync(_latest_high_watermark)
        if latest_row is None:
            return False

        latest_ts = latest_row.get("ingest_timestamp")
        latest_id = int(latest_row.get("id") or 0)
        checkpoint_ts = checkpoint.last_ingest_timestamp
        checkpoint_id = int(checkpoint.last_source_id or 0)

        if isinstance(latest_ts, str):
            latest_ts = datetime.fromisoformat(latest_ts)
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)
        if checkpoint_ts.tzinfo is None:
            checkpoint_ts = checkpoint_ts.replace(tzinfo=timezone.utc)

        if latest_ts > checkpoint_ts:
            return True
        if latest_ts == checkpoint_ts and latest_id > checkpoint_id:
            return True
        return False

    @staticmethod
    def _infer_data_domain(source_table_name: str) -> str:
        parts = source_table_name.split("_")
        if len(parts) < 4 or parts[0] != "fact":
            raise ValueError(f"Unsupported B-class table name: {source_table_name}")
        return parts[2]
