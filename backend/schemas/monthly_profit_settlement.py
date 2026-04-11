from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MonthlyProfitPersonnelDetailResponse(BaseModel):
    detail_type: str
    amount: float
    employee_code: Optional[str] = None
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    source_module: Optional[str] = None
    source_record_id: Optional[str] = None
    remark: Optional[str] = None


class MonthlyProfitFollowDetailResponse(BaseModel):
    amount: float
    status: str
    investor_user_id: Optional[int] = None
    source_settlement_id: Optional[int] = None
    remark: Optional[str] = None


class MonthlyProfitAdjustmentResponse(BaseModel):
    adjustment_type: str
    amount: float
    reason: Optional[str] = None
    created_by: Optional[str] = None


class MonthlyProfitSettlementSummaryResponse(BaseModel):
    id: Optional[int] = None
    period_month: str
    net_profit_amount: float
    personnel_target_ratio: float
    follow_target_ratio: float
    company_target_ratio: float
    personnel_target_amount: float
    follow_target_amount: float
    company_target_amount: float
    personnel_actual_amount: float
    follow_actual_amount: float
    company_actual_amount: float
    personnel_actual_ratio: float
    follow_actual_ratio: float
    company_actual_ratio: float
    adjustment_amount: float
    difference_amount: float
    difference_ratio: float
    status: str
    approved_by: Optional[str] = None
    remark: Optional[str] = None


class MonthlyProfitSettlementResponse(BaseModel):
    summary: MonthlyProfitSettlementSummaryResponse
    personnel_details: list[MonthlyProfitPersonnelDetailResponse]
    follow_details: list[MonthlyProfitFollowDetailResponse]
    adjustments: list[MonthlyProfitAdjustmentResponse]


class MonthlyProfitSettlementEnvelopeResponse(BaseModel):
    success: bool
    data: MonthlyProfitSettlementResponse
    timestamp: str


class MonthlyProfitSettlementStatusResponse(BaseModel):
    id: int
    status: str
    approved_by: Optional[str] = None


class MonthlyProfitSettlementStatusEnvelopeResponse(BaseModel):
    success: bool
    data: MonthlyProfitSettlementStatusResponse
    timestamp: str


class MonthlyProfitSettlementRebuildRequest(BaseModel):
    period_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    personnel_target_ratio: float = Field(..., ge=0, le=1)
    follow_target_ratio: float = Field(..., ge=0, le=1)
    company_target_ratio: float = Field(..., ge=0, le=1)
    adjustment_amount: float = 0.0
    adjustment_reason: Optional[str] = None


class MonthlyProfitSettlementTargetsUpdateRequest(BaseModel):
    personnel_target_ratio: float = Field(..., ge=0, le=1)
    follow_target_ratio: float = Field(..., ge=0, le=1)
    company_target_ratio: float = Field(..., ge=0, le=1)
    adjustment_amount: float = 0.0
    adjustment_reason: Optional[str] = None
