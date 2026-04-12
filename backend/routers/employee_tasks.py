from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.employee_task import EmployeeTaskSubmitRequest
from backend.services.employee_task_service import EmployeeTaskService
from backend.utils.api_response import success_response


router = APIRouter(prefix="/employee-tasks", tags=["员工任务中心"])


@router.get("")
async def list_employee_tasks(
    scope: str = Query("owner"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = EmployeeTaskService(db)
    items = await service.list_tasks_for_user(user_id=current_user.user_id, scope=scope)
    return success_response(data={"items": items, "total": len(items)})


@router.get("/{task_id}")
async def get_employee_task(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = EmployeeTaskService(db)
    try:
        task = await service.get_task_detail(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=task)


@router.post("/{task_id}/start")
async def start_employee_task(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = EmployeeTaskService(db)
    try:
        task = await service.start_task(task_id, actor_user_id=current_user.user_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return success_response(data=task)


@router.post("/{task_id}/submit")
async def submit_employee_task(
    task_id: str,
    body: EmployeeTaskSubmitRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = EmployeeTaskService(db)
    try:
        task = await service.submit_task_result(
            task_id,
            actor_user_id=current_user.user_id,
            completion_payload=body.completion_payload,
            result_comment=body.result_comment,
            requires_confirmation=body.requires_confirmation,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return success_response(data=task)
