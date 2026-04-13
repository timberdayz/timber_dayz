from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.monthly_profit_settlement import (
    MonthlyProfitSettlementEnvelopeResponse,
    MonthlyProfitSettlementRebuildRequest,
    MonthlyProfitSettlementStatusEnvelopeResponse,
    MonthlyProfitSettlementTargetsUpdateRequest,
)
from backend.services.monthly_profit_settlement_service import (
    MonthlyProfitSettlementConflictError,
    MonthlyProfitSettlementNotFoundError,
    MonthlyProfitSettlementService,
    MonthlyProfitSettlementValidationError,
)
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

router = APIRouter(prefix="/api/finance/monthly-profit-settlement", tags=["monthly-profit-settlement"])
_ALLOWED_ROLES = {"admin", "manager", "finance"}
logger = get_logger(__name__)


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


@router.get("", response_model=MonthlyProfitSettlementEnvelopeResponse)
async def get_monthly_profit_settlement(
    period_month: str = Query(..., description="month in YYYY-MM"),
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = MonthlyProfitSettlementService(db)
    payload = await service.get_month(period_month)
    return success_response(data=payload)


@router.post("/rebuild", response_model=MonthlyProfitSettlementEnvelopeResponse)
async def rebuild_monthly_profit_settlement(
    body: MonthlyProfitSettlementRebuildRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_finance_role),
):
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.rebuild_month(
            period_month=body.period_month,
            personnel_target_ratio=body.personnel_target_ratio,
            follow_target_ratio=body.follow_target_ratio,
            company_target_ratio=body.company_target_ratio,
            adjustment_amount=body.adjustment_amount,
            adjustment_reason=body.adjustment_reason,
        )
    except MonthlyProfitSettlementConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (MonthlyProfitSettlementValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settlement_id = payload.get("summary", {}).get("id")
    if settlement_id:
        try:
            from backend.services.approval_center_service import submit_monthly_profit_settlement_approval

            await submit_monthly_profit_settlement_approval(
                db=db,
                applicant_user_id=int(getattr(current_user, "user_id", 0) or 0),
                settlement_id=int(settlement_id),
                period_month=body.period_month,
            )
        except Exception as exc:
            logger.warning(f"[approval-center] failed to submit monthly profit settlement approval: {exc}")
    return success_response(data=payload)


@router.put("/{settlement_id}/targets", response_model=MonthlyProfitSettlementEnvelopeResponse)
async def update_monthly_profit_settlement_targets(
    settlement_id: int,
    body: MonthlyProfitSettlementTargetsUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.update_targets(settlement_id, body.model_dump())
    except (MonthlyProfitSettlementNotFoundError, LookupError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonthlyProfitSettlementValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (MonthlyProfitSettlementConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success_response(data=payload)


@router.post("/{settlement_id}/approve", response_model=MonthlyProfitSettlementStatusEnvelopeResponse)
async def approve_monthly_profit_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_finance_role),
):
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.approve(
            settlement_id=settlement_id,
            approver=str(getattr(current_user, "user_id", None) or getattr(current_user, "username", "") or "system"),
        )
    except (MonthlyProfitSettlementNotFoundError, LookupError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MonthlyProfitSettlementConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        from backend.services.approval_center_service import sync_monthly_profit_settlement_approval_decision

        await sync_monthly_profit_settlement_approval_decision(
            db=db,
            settlement_id=settlement_id,
            actor_user_id=int(getattr(current_user, "user_id", 0) or 0),
            action="approve",
            comment="monthly_profit_settlement approved",
        )
    except Exception as exc:
        logger.warning(f"[approval-center] failed to sync monthly profit settlement approval decision: {exc}")
    return success_response(data=payload)


@router.post("/{settlement_id}/reopen", response_model=MonthlyProfitSettlementStatusEnvelopeResponse)
async def reopen_monthly_profit_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user=Depends(_require_finance_role),
):
    service = MonthlyProfitSettlementService(db)
    try:
        payload = await service.reopen(settlement_id=settlement_id)
    except (MonthlyProfitSettlementNotFoundError, LookupError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MonthlyProfitSettlementConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success_response(data=payload)
