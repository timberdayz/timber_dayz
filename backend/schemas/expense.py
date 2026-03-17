"""
费用管理 API 契约 (Contract-First)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ExpenseCreateRequest(BaseModel):
    """创建/更新费用请求(Upsert)"""

    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(
        ..., description="费用月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"
    )
    rent: float = Field(0.0, ge=0, description="租金(CNY)")
    salary: float = Field(0.0, ge=0, description="工资(CNY)")
    utilities: float = Field(0.0, ge=0, description="水电费(CNY)")
    other_costs: float = Field(0.0, ge=0, description="其他成本(CNY)")


class ExpenseUpdateRequest(BaseModel):
    """更新费用请求"""

    rent: Optional[float] = Field(None, ge=0)
    salary: Optional[float] = Field(None, ge=0)
    utilities: Optional[float] = Field(None, ge=0)
    other_costs: Optional[float] = Field(None, ge=0)


class ExpenseResponse(BaseModel):
    """费用响应"""

    id: int
    shop_id: str
    year_month: str
    rent: float
    salary: float
    utilities: float
    other_costs: float
    total: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExpenseSummaryResponse(BaseModel):
    """费用汇总响应"""

    year_month: str
    shop_count: int
    total_rent: float
    total_salary: float
    total_utilities: float
    total_other_costs: float
    total_amount: float
