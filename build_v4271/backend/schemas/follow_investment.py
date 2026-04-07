from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FollowInvestmentCreateRequest(BaseModel):
    investor_user_id: int
    platform_code: str
    shop_id: str
    contribution_amount: float = Field(..., gt=0)
    contribution_date: str
    withdraw_date: Optional[str] = None
    capital_type: str = "working_capital"
    remark: Optional[str] = None


class FollowInvestmentUpdateRequest(BaseModel):
    contribution_amount: Optional[float] = Field(None, gt=0)
    contribution_date: Optional[str] = None
    withdraw_date: Optional[str] = None
    status: Optional[str] = None
    capital_type: Optional[str] = None
    remark: Optional[str] = None


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
