from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.dependencies.auth import require_admin
from backend.models.database import SessionLocal
from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.cloud_b_class_sync_utils import validate_b_class_table_name
from modules.core.db import CloudBClassSyncTask

router = APIRouter()


class ManualTriggerRequest(BaseModel):
    source_table_name: str = Field(pattern=r"^fact_[a-z0-9_]+$")


def build_dispatch_service():
    db = SessionLocal()

    class _Wrapper:
        def __init__(self, db_session):
            self._db_session = db_session
            self._service = CloudBClassAutoSyncDispatchService(db_session)

        def enqueue_manual(self, source_table_name: str) -> dict[str, Any]:
            from backend.utils.events import DataIngestedEvent

            validate_b_class_table_name(source_table_name)
            event = DataIngestedEvent(
                file_id=None,
                platform_code=None,
                data_domain=None,
                sub_domain=None,
                granularity=None,
                source_table_name=source_table_name,
                row_count=0,
            )
            try:
                return self._service.enqueue_or_coalesce(event)
            finally:
                self._db_session.close()

        def retry(self, job_id: str) -> dict[str, Any]:
            try:
                task = (
                    self._db_session.query(CloudBClassSyncTask)
                    .filter(CloudBClassSyncTask.job_id == job_id)
                    .one_or_none()
                )
                if task is None:
                    return {"job_id": job_id, "status": "not_found"}
                task.status = "pending"
                task.next_retry_at = None
                self._db_session.commit()
                return {"job_id": task.job_id, "status": task.status}
            finally:
                self._db_session.close()

        def list_tasks(self) -> list[dict[str, Any]]:
            try:
                tasks = (
                    self._db_session.query(CloudBClassSyncTask)
                    .order_by(CloudBClassSyncTask.id.desc())
                    .all()
                )
                return [
                    {
                        "job_id": task.job_id,
                        "status": task.status,
                        "source_table_name": task.source_table_name,
                    }
                    for task in tasks
                ]
            finally:
                self._db_session.close()

        def get_task(self, job_id: str) -> dict[str, Any]:
            try:
                task = (
                    self._db_session.query(CloudBClassSyncTask)
                    .filter(CloudBClassSyncTask.job_id == job_id)
                    .one_or_none()
                )
                if task is None:
                    return {"job_id": job_id, "status": "not_found"}
                return {
                    "job_id": task.job_id,
                    "status": task.status,
                    "source_table_name": task.source_table_name,
                }
            finally:
                self._db_session.close()

    return _Wrapper(db)


def build_health_provider():
    def _provider(request: Request | None = None) -> dict[str, Any]:
        runtime = None
        if request is not None:
            runtime = getattr(request.app.state, "cloud_sync_runtime", None)

        db = SessionLocal()
        try:
            tasks = db.query(CloudBClassSyncTask).all()
            pending = sum(1 for task in tasks if task.status == "pending")
            running = sum(1 for task in tasks if task.status == "running")
            retry_waiting = sum(1 for task in tasks if task.status == "retry_waiting")
        finally:
            db.close()

        return {
            "worker": runtime.get_health() if runtime is not None else {"status": "not_started"},
            "tunnel": {"status": "unknown"},
            "queue": {
                "pending": pending,
                "running": running,
                "retry_waiting": retry_waiting,
            },
        }

    return _provider


@router.get("/api/cloud-sync/health")
async def cloud_sync_health(request: Request, current_user=Depends(require_admin)):
    return build_health_provider()(request)


@router.post("/api/cloud-sync/tasks/trigger")
async def trigger_cloud_sync_task(payload: ManualTriggerRequest, current_user=Depends(require_admin)):
    return build_dispatch_service().enqueue_manual(payload.source_table_name)


@router.get("/api/cloud-sync/tasks")
async def list_cloud_sync_tasks(current_user=Depends(require_admin)):
    return build_dispatch_service().list_tasks()


@router.get("/api/cloud-sync/tasks/{job_id}")
async def get_cloud_sync_task(job_id: str, current_user=Depends(require_admin)):
    return build_dispatch_service().get_task(job_id)


@router.post("/api/cloud-sync/tasks/{job_id}/retry")
async def retry_cloud_sync_task(job_id: str, current_user=Depends(require_admin)):
    return build_dispatch_service().retry(job_id)
