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


class FollowInvestmentResponse(BaseModel):
    id: int
    investor_user_id: int
    investor_name: Optional[str] = None
    platform_code: str
    shop_id: str
    contribution_amount: float
    contribution_date: str
    withdraw_date: Optional[str] = None
    capital_type: str
    status: str
    remark: Optional[str] = None


class FollowInvestmentSettlementSummaryResponse(BaseModel):
    id: int
    period_month: str
    platform_code: str
    shop_id: str
    profit_basis_amount: float
    distribution_ratio: float
    distributable_amount: float
    status: str
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[str] = None


class FollowInvestmentSettlementDetailResponse(BaseModel):
    investor_user_id: int
    investor_name: Optional[str] = None
    contribution_amount_snapshot: float
    occupied_days: int
    weighted_capital: float
    share_ratio: float
    estimated_income: float
    approved_income: float = 0.0
    paid_income: float = 0.0


class FollowInvestmentSettlementCalculatePayloadResponse(BaseModel):
    settlement: FollowInvestmentSettlementSummaryResponse
    details: list[FollowInvestmentSettlementDetailResponse]


class FollowInvestmentMyIncomeSummaryResponse(BaseModel):
    estimated_income: float
    approved_income: float
    paid_income: float
    current_contribution_amount: float


class FollowInvestmentMyIncomeItemResponse(BaseModel):
    period_month: str
    platform_code: str
    shop_id: str
    investor_name: str
    profit_basis_amount: float
    share_ratio: float
    estimated_income: float
    approved_income: float
    paid_income: float
    approved_at: Optional[str] = None
    status: str


class FollowInvestmentMyIncomeResponse(BaseModel):
    summary: FollowInvestmentMyIncomeSummaryResponse
    items: list[FollowInvestmentMyIncomeItemResponse]


class FollowInvestmentSettlementStatusResponse(BaseModel):
    id: int
    status: str
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None


class SuccessEnvelopeBase(BaseModel):
    success: bool
    timestamp: str


class FollowInvestmentEnvelopeResponse(SuccessEnvelopeBase):
    data: FollowInvestmentResponse


class FollowInvestmentListEnvelopeResponse(SuccessEnvelopeBase):
    data: list[FollowInvestmentResponse]


class FollowInvestmentSettlementCalculateEnvelopeResponse(SuccessEnvelopeBase):
    data: FollowInvestmentSettlementCalculatePayloadResponse


class FollowInvestmentSettlementListEnvelopeResponse(SuccessEnvelopeBase):
    data: list[FollowInvestmentSettlementSummaryResponse]


class FollowInvestmentSettlementDetailsEnvelopeResponse(SuccessEnvelopeBase):
    data: list[FollowInvestmentSettlementDetailResponse]


class FollowInvestmentMyIncomeEnvelopeResponse(SuccessEnvelopeBase):
    data: FollowInvestmentMyIncomeResponse


class FollowInvestmentSettlementStatusEnvelopeResponse(SuccessEnvelopeBase):
    data: FollowInvestmentSettlementStatusResponse
