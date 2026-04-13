from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.approval_center import ApprovalActionRequest
from backend.services.approval_center_service import ApprovalCenterService
from backend.utils.api_response import success_response
from modules.core.db import ApprovalInstance


router = APIRouter(prefix="/approval-center", tags=["审批中心"])


@router.get("/requests")
async def list_my_requests(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(ApprovalInstance)
            .where(ApprovalInstance.applicant_user_id == current_user.user_id)
            .order_by(ApprovalInstance.created_at.desc(), ApprovalInstance.id.desc())
        )
    ).scalars().all()
    items = [
        {
            "approval_id": row.approval_id,
            "template_code": row.template_code,
            "status": row.status,
            "current_step": row.current_step,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
        for row in rows
    ]
    return success_response(data={"items": items, "total": len(items)})


@router.get("/{approval_id:path}")
async def get_approval_detail(
    approval_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = ApprovalCenterService(db)
    try:
        payload = await service.get_approval_detail(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=payload)


@router.post("/{approval_id:path}/approve")
async def approve_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = ApprovalCenterService(db)
    payload = await service.approve_step(approval_id, actor_user_id=current_user.user_id, comment=body.comment)
    return success_response(data=payload)


@router.post("/{approval_id:path}/reject")
async def reject_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = ApprovalCenterService(db)
    payload = await service.reject_step(approval_id, actor_user_id=current_user.user_id, comment=body.comment)
    return success_response(data=payload)


@router.post("/{approval_id:path}/withdraw")
async def withdraw_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = ApprovalCenterService(db)
    payload = await service.withdraw_approval(approval_id, actor_user_id=current_user.user_id, comment=body.comment)
    return success_response(data=payload)
