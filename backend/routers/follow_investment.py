from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.follow_investment import FollowInvestmentSettlementCalculateRequest
from backend.services.follow_investment_service import FollowInvestmentService
from backend.utils.api_response import success_response

router = APIRouter(prefix="/api/finance/follow-investments", tags=["follow-investment"])
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


@router.post("/settlements/calculate")
async def calculate_follow_investment_settlement(
    body: FollowInvestmentSettlementCalculateRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = FollowInvestmentService(db)
    payload = await service.calculate_settlement(
        year_month=body.period_month,
        platform_code=body.platform_code,
        shop_id=body.shop_id,
        distribution_ratio=body.distribution_ratio,
    )
    return success_response(data=payload)


@router.get("/my-income")
async def get_my_follow_investment_income(
    period_month: str | None = Query(None, description="month in YYYY-MM"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    service = FollowInvestmentService(db)
    payload = await service.get_my_income(
        user_id=int(getattr(current_user, "user_id", 0) or 0),
        period_month=period_month,
    )
    return success_response(data=payload)
