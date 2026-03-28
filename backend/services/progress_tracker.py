"""
批量入库进度跟踪服务

兼容层职责:
- 维持 legacy field-mapping / auto-ingest 进度接口
- 底层持久化迁移到 task center
- 允许保留旧实现中任意附加字段的读写
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.services.task_center_service import TaskCenterService
from backend.utils.data_formatter import format_datetime


class ProgressTracker:
    """Task-center-backed compatibility wrapper for legacy progress APIs."""

    TASK_FAMILY = "legacy_field_mapping"

    def __init__(self, async_session_factory=None):
        if async_session_factory is None:
            from backend.models.database import AsyncSessionLocal

            async_session_factory = AsyncSessionLocal
        self._session_factory = async_session_factory

    async def create_task(
        self,
        task_id: str,
        total_files: int,
        task_type: str = "bulk_ingest",
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            service = TaskCenterService(session)
            existing = await service.get_task(task_id)
            if existing:
                return self._task_to_dict(existing)

            task = await service.create_task(
                task_id=task_id,
                task_family=self.TASK_FAMILY,
                task_type=task_type,
                status="pending",
                total_items=total_files,
                processed_items=0,
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
                    "legacy_fields": {},
                    "row_progress": 0.0,
                },
            )
            return self._task_to_dict(task)

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        async with self._session_factory() as session:
            service = TaskCenterService(session)
            current = await service.get_task(task_id)
            if not current:
                raise ValueError(f"Task {task_id} not found")

            payload = self._legacy_updates_to_task_center(current, updates)
            updated = await service.update_task(task_id, **payload)
            return self._task_to_dict(updated)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            task = await TaskCenterService(session).get_task(task_id)
            if not task:
                return None
            return self._task_to_dict(task)

    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
        error: str = None,
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            service = TaskCenterService(session)
            current = await service.get_task(task_id)
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

            updated = await service.update_task(
                task_id,
                status="completed" if success else "failed",
                finished_at=datetime.now(timezone.utc),
                error_summary=error if error else current.get("error_summary"),
                details_json=details,
            )
            return self._task_to_dict(updated)

    async def add_error(self, task_id: str, error: str) -> None:
        async with self._session_factory() as session:
            service = TaskCenterService(session)
            current = await service.get_task(task_id)
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
            await service.update_task(task_id, error_summary=error, details_json=details)

    async def add_warning(self, task_id: str, warning: str) -> None:
        async with self._session_factory() as session:
            service = TaskCenterService(session)
            current = await service.get_task(task_id)
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
            await service.update_task(task_id, details_json=details)

    async def delete_task(self, task_id: str) -> bool:
        async with self._session_factory() as session:
            return await TaskCenterService(session).delete_task(task_id)

    async def list_tasks(self, status: str = None) -> list:
        async with self._session_factory() as session:
            rows = await TaskCenterService(session).list_tasks(
                task_family=self.TASK_FAMILY,
                status=self._legacy_status_to_task_center(status) if status else None,
            )
            return [self._task_to_dict(row) for row in rows]

    def _legacy_updates_to_task_center(
        self,
        current: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        details = self._details_from_task_center(current)
        legacy_fields = dict(details.get("legacy_fields", {}))

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

        for key, value in updates.items():
            if key in field_map:
                payload[field_map[key]] = value
            elif key == "status":
                payload["status"] = self._legacy_status_to_task_center(value)
            elif key == "file_progress":
                payload["progress_percent"] = value
            elif key == "row_progress":
                details["row_progress"] = value
            else:
                legacy_fields[key] = value

        total_items = payload.get("total_items", current.get("total_items", 0)) or 0
        processed_items = payload.get("processed_items", current.get("processed_items", 0)) or 0
        if "progress_percent" not in payload and total_items > 0:
            payload["progress_percent"] = round(processed_items / total_items * 100, 2)

        total_rows = payload.get("total_rows", current.get("total_rows", 0)) or 0
        processed_rows = payload.get("processed_rows", current.get("processed_rows", 0)) or 0
        if "row_progress" not in details and total_rows > 0:
            details["row_progress"] = round(processed_rows / total_rows * 100, 2)
        elif total_rows > 0 and "processed_rows" in payload:
            details["row_progress"] = round(processed_rows / total_rows * 100, 2)

        details["legacy_fields"] = legacy_fields
        payload["details_json"] = details
        return payload

    def _task_to_dict(self, task: Dict[str, Any]) -> Dict[str, Any]:
        details = self._details_from_task_center(task)
        legacy_fields = dict(details.get("legacy_fields", {}))
        total_rows = task.get("total_rows", 0) or 0
        processed_rows = task.get("processed_rows", 0) or 0
        row_progress = details.get("row_progress")
        if row_progress is None and total_rows > 0:
            row_progress = round(processed_rows / total_rows * 100, 2)
        elif row_progress is None:
            row_progress = 0.0

        payload = {
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
            "errors": details.get("errors", []),
            "warnings": details.get("warnings", []),
            "updated_at": format_datetime(task.get("updated_at")),
        }
        payload.update(legacy_fields)
        return payload

    @staticmethod
    def _details_from_task_center(task: Dict[str, Any]) -> Dict[str, Any]:
        details = task.get("details_json") or {}
        return {
            "errors": list(details.get("errors", [])),
            "warnings": list(details.get("warnings", [])),
            "legacy_fields": dict(details.get("legacy_fields", {})),
            "row_progress": details.get("row_progress"),
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


progress_tracker = ProgressTracker()
