from __future__ import annotations

from pydantic import BaseModel, Field


class FollowInvestmentSettlementCalculateRequest(BaseModel):
    period_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    platform_code: str
    shop_id: str
    distribution_ratio: float = Field(..., ge=0, le=1)


class FollowInvestmentSettlementDetailResponse(BaseModel):
    investor_user_id: int
    contribution_amount_snapshot: float
    occupied_days: int
    weighted_capital: float
    share_ratio: float
    estimated_income: float


class FollowInvestmentSettlementResponse(BaseModel):
    period_month: str
    platform_code: str
    shop_id: str
    profit_basis_amount: float
    distribution_ratio: float
    distributable_amount: float
