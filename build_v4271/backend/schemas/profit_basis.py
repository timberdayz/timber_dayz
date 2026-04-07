from __future__ import annotations

from pydantic import BaseModel, Field


class ProfitBasisResponse(BaseModel):
    period_month: str
    platform_code: str
    shop_id: str
    orders_profit_amount: float
    a_class_cost_amount: float
    b_class_cost_amount: float
    profit_basis_amount: float
    basis_version: str


class ProfitBasisRebuildRequest(BaseModel):
    period_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    platform_code: str
    shop_id: str
    basis_version: str = "A_ONLY_V1"
