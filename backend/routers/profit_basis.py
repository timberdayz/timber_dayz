from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.profit_basis import ProfitBasisRebuildRequest
from backend.services.profit_basis_service import ProfitBasisService
from backend.utils.api_response import success_response

router = APIRouter(prefix="/api/finance", tags=["profit-basis"])
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


@router.get("/profit-basis")
async def get_profit_basis(
    period_month: str = Query(..., description="month in YYYY-MM"),
    platform_code: str = Query(...),
    shop_id: str = Query(...),
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = ProfitBasisService(db)
    payload = await service.build_profit_basis(
        year_month=period_month,
        platform_code=platform_code,
        shop_id=shop_id,
    )
    return success_response(data=payload)


@router.post("/profit-basis/rebuild")
async def rebuild_profit_basis(
    body: ProfitBasisRebuildRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = ProfitBasisService(db)
    payload = await service.build_profit_basis(
        year_month=body.period_month,
        platform_code=body.platform_code,
        shop_id=body.shop_id,
        basis_version=body.basis_version,
    )
    return success_response(data=payload)
