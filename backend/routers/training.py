from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user, is_admin_or_manager_user, require_admin, require_admin_or_manager
from backend.models.database import get_async_db
from backend.schemas.training import (
    TrainingAssignmentCreateRequest,
    TrainingFeishuConfigUpdateRequest,
    TrainingFeishuSyncRequest,
    TrainingProgramCreateRequest,
    TrainingProgramFeishuBindingRequest,
    TrainingResultUpdateRequest,
)
from backend.services.training_service import TrainingService
from backend.utils.api_response import success_response


router = APIRouter(prefix="/training", tags=["培训管理"])


@router.get("/overview")
async def get_training_overview(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).get_overview())


@router.get("/programs")
async def list_training_programs(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).list_programs())


@router.post("/programs")
async def create_training_program(
    body: TrainingProgramCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).create_program(body.model_dump()))


@router.put("/programs/{program_id}/feishu-binding")
async def bind_training_program_feishu(
    program_id: str,
    body: TrainingProgramFeishuBindingRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    _ = current_user
    try:
        payload = await TrainingService(db).bind_program_feishu(program_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=payload)


@router.get("/assignments")
async def list_training_assignments(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).list_assignments())


@router.get("/assignments/{assignment_id}")
async def get_training_assignment_detail(
    assignment_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        payload = await TrainingService(db).get_assignment_detail(assignment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not is_admin_or_manager_user(current_user):
        current_employee_code = getattr(current_user, "employee_code", None)
        if not current_employee_code or current_employee_code != payload["employee_code"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    return success_response(data=payload)


@router.post("/assignments")
async def create_training_assignment(
    body: TrainingAssignmentCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).create_assignment(body.model_dump()))


@router.get("/results")
async def list_training_results(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    return success_response(data=await TrainingService(db).list_results())


@router.put("/results/{assignment_id}")
async def update_training_result(
    assignment_id: str,
    body: TrainingResultUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_or_manager),
):
    _ = current_user
    try:
        payload = await TrainingService(db).update_result(assignment_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=payload)


@router.get("/my-overview")
async def get_my_training_overview(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    employee_code = getattr(current_user, "employee_code", None)
    if not is_admin_or_manager_user(current_user) and not employee_code:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return success_response(data=await TrainingService(db).get_my_overview(employee_code=employee_code))


@router.get("/integrations/feishu/config")
async def get_feishu_training_config(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    _ = current_user
    return success_response(data=await TrainingService(db).get_feishu_config())


@router.put("/integrations/feishu/config")
async def update_feishu_training_config(
    body: TrainingFeishuConfigUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    return success_response(
        data=await TrainingService(db).upsert_feishu_config(
            body.model_dump(),
            updated_by_user_id=current_user.user_id,
        )
    )


@router.post("/integrations/feishu/sync-results")
async def sync_training_results_from_feishu(
    body: TrainingFeishuSyncRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    _ = current_user
    try:
        payload = await TrainingService(db).sync_feishu_results(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=payload)
