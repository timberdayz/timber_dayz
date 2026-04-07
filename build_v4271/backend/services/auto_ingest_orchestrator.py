#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legacy auto-ingest compatibility wrapper.

Runtime orchestration has converged on `DataSyncService`. This module remains
only to keep historical imports callable while delegating into the unified
sync path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_sync_service import DataSyncService
from backend.services.progress_tracker import progress_tracker
from modules.core.db import CatalogFile
from modules.core.logger import get_logger

logger = get_logger(__name__)


def _is_no_template_result(result: Dict[str, Any]) -> bool:
    if result.get("status") != "skipped":
        return False
    message = str(result.get("message", ""))
    message_lower = message.lower()
    return (
        "no_template" in message_lower
        or "no template" in message_lower
        or "无模板" in message
    )


class AutoIngestOrchestrator:
    """Compatibility facade that delegates legacy auto-ingest calls."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.progress_tracker = progress_tracker
        self.sync_service = DataSyncService(db)

    async def ingest_single_file(
        self,
        file_id: int,
        only_with_template: bool = True,
        allow_quarantine: bool = True,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegate single-file auto-ingest to the unified sync service."""
        return await self.sync_service.sync_single_file(
            file_id=file_id,
            only_with_template=only_with_template,
            allow_quarantine=allow_quarantine,
            task_id=task_id,
            use_template_header_row=True,
        )

    async def batch_ingest(
        self,
        platform: Optional[str] = None,
        domains: List[str] | None = None,
        granularities: List[str] | None = None,
        since_hours: int | None = None,
        limit: int = 100,
        only_with_template: bool = True,
        allow_quarantine: bool = True,
    ) -> Dict[str, Any]:
        """Select pending files and process them through `DataSyncService`."""
        stmt = select(CatalogFile).where(CatalogFile.status == "pending")

        normalized_platform: Optional[str] = None
        if platform and platform.strip():
            platform = platform.strip()
            if platform not in ("*", "all", "ALL"):
                normalized_platform = platform.lower()

        if normalized_platform:
            stmt = stmt.where(
                or_(
                    func.lower(CatalogFile.platform_code) == normalized_platform,
                    func.lower(CatalogFile.source_platform) == normalized_platform,
                )
            )

        if domains:
            stmt = stmt.where(CatalogFile.data_domain.in_(domains))
        if granularities:
            stmt = stmt.where(CatalogFile.granularity.in_(granularities))
        if since_hours:
            since_time = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            stmt = stmt.where(CatalogFile.first_seen_at >= since_time)

        stmt = stmt.order_by(CatalogFile.first_seen_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        files = result.scalars().all()
        total_files = len(files)

        if total_files == 0:
            return {
                "success": True,
                "task_id": None,
                "summary": {
                    "total_files": 0,
                    "processed": 0,
                    "succeeded": 0,
                    "quarantined": 0,
                    "failed": 0,
                    "skipped_no_template": 0,
                },
                "files": [],
                "message": "没有符合条件的待入库文件",
            }

        task_id = str(uuid4())
        await self.progress_tracker.create_task(task_id, total_files, task_type="auto_ingest")
        await self.progress_tracker.update_task(
            task_id,
            {
                "status": "processing",
                "total": total_files,
                "processed": 0,
                "succeeded": 0,
                "quarantined": 0,
                "failed": 0,
                "skipped": 0,
                "files": [],
            },
        )

        succeeded = 0
        quarantined = 0
        failed = 0
        skipped_no_template = 0
        processed_files: List[Dict[str, Any]] = []

        for idx, file_record in enumerate(files):
            try:
                item = await self.sync_service.sync_single_file(
                    file_id=file_record.id,
                    only_with_template=only_with_template,
                    allow_quarantine=allow_quarantine,
                    task_id=task_id,
                    use_template_header_row=True,
                )
            except Exception as file_error:
                logger.error(
                    "[AutoIngestLegacy] 批量处理文件失败: file_id=%s, error=%s",
                    file_record.id,
                    file_error,
                    exc_info=True,
                )
                item = {
                    "success": False,
                    "file_id": file_record.id,
                    "status": "failed",
                    "message": str(file_error),
                }

            status = item.get("status")
            if status == "success":
                succeeded += 1
            elif status == "quarantined":
                quarantined += 1
            elif status == "failed":
                failed += 1
            elif _is_no_template_result(item):
                skipped_no_template += 1

            processed_files.append(item)

            await self.progress_tracker.update_task(
                task_id,
                {
                    "processed_files": idx + 1,
                    "processed": idx + 1,
                    "valid_rows": succeeded,
                    "succeeded": succeeded,
                    "quarantined_rows": quarantined,
                    "quarantined": quarantined,
                    "error_rows": failed,
                    "failed": failed,
                    "skipped": skipped_no_template,
                    "files": processed_files[-10:],
                },
            )

        await self.progress_tracker.complete_task(task_id, success=True)

        return {
            "success": True,
            "task_id": task_id,
            "summary": {
                "total_files": total_files,
                "processed": total_files,
                "succeeded": succeeded,
                "quarantined": quarantined,
                "failed": failed,
                "skipped_no_template": skipped_no_template,
            },
            "files": processed_files,
        }


def get_auto_ingest_orchestrator(db: AsyncSession) -> AutoIngestOrchestrator:
    """Return the legacy compatibility wrapper."""
    return AutoIngestOrchestrator(db)
