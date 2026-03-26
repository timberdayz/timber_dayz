from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.services.cloud_sync_admin_command_service import CloudSyncAdminCommandService
from backend.services.cloud_sync_admin_query_service import CloudSyncAdminQueryService

router = APIRouter()


class ManualTriggerRequest(BaseModel):
    source_table_name: str = Field(pattern=r"^fact_[a-z0-9_]+$")


def build_query_service(db: AsyncSession) -> CloudSyncAdminQueryService:
    return CloudSyncAdminQueryService(db)


def build_command_service(db: AsyncSession) -> CloudSyncAdminCommandService:
    return CloudSyncAdminCommandService(db)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


@router.get("/api/cloud-sync/health")
async def cloud_sync_health(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    runtime = getattr(request.app.state, "cloud_sync_runtime", None)
    runtime_health = runtime.get_health() if runtime is not None else None
    service = build_query_service(db)
    return await _maybe_await(service.get_health_summary(runtime_health=runtime_health))


@router.get("/api/cloud-sync/tables")
async def list_cloud_sync_tables(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_query_service(db)
    return await _maybe_await(service.list_table_states())


@router.post("/api/cloud-sync/tasks/trigger")
async def trigger_cloud_sync_task(
    payload: ManualTriggerRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.trigger_sync(payload.source_table_name))


@router.get("/api/cloud-sync/tasks")
async def list_cloud_sync_tasks(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_query_service(db)
    return await _maybe_await(service.list_tasks())


@router.get("/api/cloud-sync/tasks/{job_id}")
async def get_cloud_sync_task(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_query_service(db)
    task = await _maybe_await(service.get_task(job_id))
    if task is None:
        return {"job_id": job_id, "status": "not_found"}
    return task


@router.post("/api/cloud-sync/tasks/{job_id}/retry")
async def retry_cloud_sync_task(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.retry_task(job_id))


@router.post("/api/cloud-sync/tasks/{job_id}/cancel")
async def cancel_cloud_sync_task(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.cancel_task(job_id))


@router.post("/api/cloud-sync/tables/{table_name}/dry-run")
async def dry_run_cloud_sync_table(
    table_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.dry_run_table(table_name))


@router.post("/api/cloud-sync/tables/{table_name}/repair-checkpoint")
async def repair_cloud_sync_checkpoint(
    table_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.repair_checkpoint(table_name))


@router.post("/api/cloud-sync/tables/{table_name}/refresh-projection")
async def refresh_cloud_sync_projection(
    table_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = build_command_service(db)
    return await _maybe_await(service.refresh_projection(table_name))
