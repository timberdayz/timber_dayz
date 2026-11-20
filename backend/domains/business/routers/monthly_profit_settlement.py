from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.monthly_profit_settlement import (
    MonthlyProfitAdjustmentCreateRequest,
    MonthlyProfitAdjustmentDeleteEnvelopeResponse,
    MonthlyProfitAdjustmentEnvelopeResponse,
    MonthlyProfitDashboardEnvelopeResponse,
)
from backend.services.monthly_profit_settlement_service import (
    MonthlyProfitSettlementNotFoundError,
    MonthlyProfitSettlementService,
    MonthlyProfitSettlementValidationError,
)
from backend.utils.api_response import success_response

router = APIRouter(
    prefix="/api/finance/monthly-profit-settlement", tags=["monthly-profit-settlement"]
)
_ALLOWED_ROLES = {"admin", "manager", "finance"}


def _extract_role_codes(current_user) -> set[str]:
    role_codes: set[str] = set()
    for role in getattr(current_user, "roles", []) or []:
        role_code = getattr(role, "role_code", None)
        role_name = getattr(role, "role_name", None)
        if role_code:
            role_codes.add(str(role_code).lower())
        if role_name:
            role_codes.add(str(role_name).lower())
    return role_codes


def _require_finance_role(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False):
        return current_user
    if _extract_role_codes(current_user) & _ALLOWED_ROLES:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("", response_model=MonthlyProfitDashboardEnvelopeResponse)
async def get_monthly_profit_dashboard(
    period_month: str = Query(..., description="month in YYYY-MM"),
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    """月度利润看板（只读）：赚了多少 / 分给员工多少 / 人工调整多少 / 留下多少。"""
    service = MonthlyProfitSettlementService(db)
    payload = await service.get_dashboard(period_month)
    return success_response(data=payload)


@router.post("/adjustments", response_model=MonthlyProfitAdjustmentEnvelopeResponse)
async def create_monthly_profit_adjustment(
    body: MonthlyProfitAdjustmentCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_finance_role),
):
    """新增一条人工调整项（看板唯一允许的写入口）。"""
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.add_adjustment(
            period_month=body.period_month,
            adjustment_type=body.adjustment_type,
            amount=body.amount,
            reason=body.reason,
            created_by=str(getattr(current_user, "user_id", None) or "system"),
        )
    except MonthlyProfitSettlementValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=payload)


@router.delete(
    "/adjustments/{adjustment_id}",
    response_model=MonthlyProfitAdjustmentDeleteEnvelopeResponse,
)
async def delete_monthly_profit_adjustment(
    adjustment_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    """删除一条人工调整项。"""
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.remove_adjustment(adjustment_id)
    except (MonthlyProfitSettlementNotFoundError, LookupError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=payload)
