#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步进度跟踪服务(Sync Progress Tracker)

兼容层职责:
- 保持现有 data-sync 任务跟踪接口和返回字段
- 将底层存储切换到 task center
- 在内部将 legacy `processing` 状态映射到 canonical `running`
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.task_center_service import TaskCenterService
from backend.utils.data_formatter import format_datetime
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SyncProgressTracker:
    """Data-sync progress compatibility adapter backed by task center."""

    TASK_FAMILY = "data_sync"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_center = TaskCenterService(db)

    async def create_task(
        self,
        task_id: str,
        total_files: int,
        task_type: str = "bulk_ingest",
    ) -> Dict[str, Any]:
        try:
            existing_task = await self.task_center.get_task(task_id)
            if existing_task:
                logger.warning(
                    "[SyncProgress] Task %s already exists in task center, returning existing row",
                    task_id,
                )
                return self._task_to_dict(existing_task)

            task = await self.task_center.create_task(
                task_id=task_id,
                task_family=self.TASK_FAMILY,
                task_type=task_type,
                status="pending",
                total_items=total_files,
                processed_items=0,
                success_items=0,
                failed_items=0,
                skipped_items=0,
                total_rows=0,
                processed_rows=0,
                valid_rows=0,
                error_rows=0,
                quarantined_rows=0,
                progress_percent=0.0,
                started_at=datetime.now(timezone.utc),
                details_json={
                    "errors": [],
                    "warnings": [],
                    "message": None,
                    "row_progress": 0.0,
                    "task_details": {},
                },
            )
            logger.info("[SyncProgress] Created task %s: %s files", task_id, total_files)
            return self._task_to_dict(task)
        except Exception as e:
            logger.error("[SyncProgress] Failed to create task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()
            raise

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            current = await self.task_center.get_task(task_id)
            if not current:
                raise ValueError(f"Task {task_id} not found")

            payload = self._legacy_updates_to_task_center(current, updates)
            updated = await self.task_center.update_task(task_id, **payload)
            return self._task_to_dict(updated)
        except Exception as e:
            logger.error("[SyncProgress] Failed to update task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()
            raise

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                try:
                    await self.db.rollback()
                except Exception:
                    pass

                task = await self.task_center.get_task(task_id)
                if not task:
                    return None
                return self._task_to_dict(task)
            except Exception as query_error:
                error_str = str(query_error)
                is_transaction_error = (
                    "InFailedSqlTransaction" in error_str
                    or "current transaction is aborted" in error_str.lower()
                    or "transaction" in error_str.lower()
                )

                if is_transaction_error and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.warning(
                        "[SyncProgress] Transaction error detected (retry %s/%s), rolling back: %s",
                        retry_count,
                        max_retries,
                        query_error,
                    )
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass
                    await asyncio.sleep(0.1 * retry_count)
                    continue

                logger.error(
                    "[SyncProgress] Failed to get task %s (retry %s/%s): %s",
                    task_id,
                    retry_count,
                    max_retries,
                    query_error,
                    exc_info=True,
                )
                try:
                    await self.db.rollback()
                except Exception:
                    pass
                return None

        return None

    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            current = await self.task_center.get_task(task_id)
            if not current:
                raise ValueError(f"Task {task_id} not found")

            details = self._details_from_task_center(current)
            if error:
                errors = list(details.get("errors", []))
                errors.append(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "message": error,
                    }
                )
                details["errors"] = errors
                details["message"] = error

            updated = await self.task_center.update_task(
                task_id,
                status="completed" if success else "failed",
                finished_at=datetime.now(timezone.utc),
                error_summary=error if error else current.get("error_summary"),
                details_json=details,
            )
            logger.info(
                "[SyncProgress] Completed task %s: %s",
                task_id,
                "success" if success else "failed",
            )
            return self._task_to_dict(updated)
        except Exception as e:
            logger.error("[SyncProgress] Failed to complete task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()
            raise

    async def add_error(self, task_id: str, error: str) -> None:
        try:
            current = await self.task_center.get_task(task_id)
            if not current:
                return

            details = self._details_from_task_center(current)
            errors = list(details.get("errors", []))
            errors.append(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "message": error,
                }
            )
            details["errors"] = errors
            details["message"] = error

            await self.task_center.update_task(
                task_id,
                error_summary=error,
                details_json=details,
            )
        except Exception as e:
            logger.error("[SyncProgress] Failed to add error to task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()

    async def add_warning(self, task_id: str, warning: str) -> None:
        try:
            current = await self.task_center.get_task(task_id)
            if not current:
                return

            details = self._details_from_task_center(current)
            warnings = list(details.get("warnings", []))
            warnings.append(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "message": warning,
                }
            )
            details["warnings"] = warnings

            await self.task_center.update_task(task_id, details_json=details)
        except Exception as e:
            logger.error("[SyncProgress] Failed to add warning to task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        try:
            rows = await self.task_center.list_tasks(
                task_family=self.TASK_FAMILY,
                status=self._legacy_status_to_task_center(status) if status else None,
                limit=limit,
            )
            return [self._task_to_dict(row) for row in rows]
        except Exception as e:
            logger.error("[SyncProgress] Failed to list tasks: %s", e, exc_info=True)
            return []

    async def delete_task(self, task_id: str) -> bool:
        try:
            deleted = await self.task_center.delete_task(task_id)
            if deleted:
                logger.info("[SyncProgress] Deleted task %s", task_id)
            return deleted
        except Exception as e:
            logger.error("[SyncProgress] Failed to delete task %s: %s", task_id, e, exc_info=True)
            await self.db.rollback()
            return False

    def _legacy_updates_to_task_center(
        self,
        current: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        details = self._details_from_task_center(current)

        field_map = {
            "task_type": "task_type",
            "total_files": "total_items",
            "processed_files": "processed_items",
            "current_file": "current_item",
            "total_rows": "total_rows",
            "processed_rows": "processed_rows",
            "valid_rows": "valid_rows",
            "error_rows": "error_rows",
            "quarantined_rows": "quarantined_rows",
        }
        for legacy_key, task_center_key in field_map.items():
            if legacy_key in updates:
                payload[task_center_key] = updates[legacy_key]

        if "status" in updates:
            payload["status"] = self._legacy_status_to_task_center(updates["status"])

        if "message" in updates:
            details["message"] = updates["message"]

        if "task_details" in updates:
            current_task_details = details.get("task_details", {})
            new_task_details = updates["task_details"]
            if isinstance(current_task_details, dict) and isinstance(new_task_details, dict):
                details["task_details"] = {**current_task_details, **new_task_details}
            else:
                details["task_details"] = new_task_details

        if "row_progress" in updates:
            details["row_progress"] = updates["row_progress"]

        total_items = payload.get("total_items", current.get("total_items", 0)) or 0
        processed_items = payload.get("processed_items", current.get("processed_items", 0)) or 0
        if "file_progress" in updates:
            payload["progress_percent"] = updates["file_progress"]
        elif total_items > 0:
            payload["progress_percent"] = round(processed_items / total_items * 100, 2)

        total_rows = payload.get("total_rows", current.get("total_rows", 0)) or 0
        processed_rows = payload.get("processed_rows", current.get("processed_rows", 0)) or 0
        if "row_progress" not in details and total_rows > 0:
            details["row_progress"] = round(processed_rows / total_rows * 100, 2)
        elif total_rows > 0 and "processed_rows" in payload:
            details["row_progress"] = round(processed_rows / total_rows * 100, 2)

        payload["details_json"] = details
        return payload

    def _task_to_dict(self, task: Dict[str, Any]) -> Dict[str, Any]:
        details = self._details_from_task_center(task)
        task_details = details.get("task_details", {})
        errors = details.get("errors", [])
        warnings = details.get("warnings", [])
        total_rows = task.get("total_rows", 0) or 0
        processed_rows = task.get("processed_rows", 0) or 0

        row_progress = details.get("row_progress")
        if row_progress is None and total_rows > 0:
            row_progress = round(processed_rows / total_rows * 100, 2)
        elif row_progress is None:
            row_progress = 0.0

        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "total_files": task.get("total_items", 0) or 0,
            "processed_files": task.get("processed_items", 0) or 0,
            "current_file": task.get("current_item") or "",
            "status": self._task_center_status_to_legacy(task.get("status")),
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "valid_rows": task.get("valid_rows", 0) or 0,
            "error_rows": task.get("error_rows", 0) or 0,
            "quarantined_rows": task.get("quarantined_rows", 0) or 0,
            "file_progress": task.get("progress_percent", 0.0) or 0.0,
            "row_progress": row_progress,
            "start_time": format_datetime(task.get("started_at") or task.get("created_at")),
            "end_time": format_datetime(task.get("finished_at")),
            "updated_at": format_datetime(task.get("updated_at")),
            "errors": errors,
            "message": details.get("message") or self._extract_message_from_errors(errors),
            "warnings": warnings,
            "task_details": task_details,
            "success_files": task_details.get("success_files", 0),
            "failed_files": task_details.get("failed_files", 0),
            "skipped_files": task_details.get("skipped_files", 0),
        }

    @staticmethod
    def _details_from_task_center(task: Dict[str, Any]) -> Dict[str, Any]:
        details = task.get("details_json") or {}
        return {
            "errors": list(details.get("errors", [])),
            "warnings": list(details.get("warnings", [])),
            "message": details.get("message"),
            "row_progress": details.get("row_progress"),
            "task_details": dict(details.get("task_details", {})),
        }

    @staticmethod
    def _legacy_status_to_task_center(status: Optional[str]) -> Optional[str]:
        if status is None:
            return None
        return {"processing": "running"}.get(status, status)

    @staticmethod
    def _task_center_status_to_legacy(status: Optional[str]) -> Optional[str]:
        if status is None:
            return None
        return {"running": "processing"}.get(status, status)

    def _extract_message_from_errors(self, errors: List[Dict[str, Any]]) -> Optional[str]:
        if not errors:
            return None

        last_error = errors[-1]
        if isinstance(last_error, dict):
            return last_error.get("message")
        if isinstance(last_error, str):
            return last_error
        return str(last_error)
