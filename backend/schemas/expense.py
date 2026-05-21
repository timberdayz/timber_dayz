"""
费用管理 API 契约 (Contract-First)
"""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


class ExpenseCreateRequest(BaseModel):
    """创建/更新费用请求(Upsert)"""

    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(
        ..., description="费用月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"
    )
    rent: float = Field(0.0, ge=0, description="租金(CNY)")
    marketing_fee: float = Field(0.0, ge=0, description="营销费用(CNY)")
    utilities: float = Field(0.0, ge=0, description="水电费(CNY)")
    ai_token_cost: float = Field(0.0, ge=0, description="AI Token费用(CNY)")
    other_costs: float = Field(0.0, ge=0, description="其他成本(CNY)")
    note: Optional[str] = Field(None, description="备注")
    attachments: Optional[list[Any]] = Field(None, description="附件(JSON数组)")


class ExpenseUpdateRequest(BaseModel):
    """更新费用请求"""

    rent: Optional[float] = Field(None, ge=0)
    marketing_fee: Optional[float] = Field(None, ge=0)
    utilities: Optional[float] = Field(None, ge=0)
    ai_token_cost: Optional[float] = Field(None, ge=0)
    other_costs: Optional[float] = Field(None, ge=0)
    note: Optional[str] = Field(None)
    attachments: Optional[list[Any]] = Field(None)


class ExpenseResponse(BaseModel):
    """费用响应"""

    id: int
    shop_id: str
    year_month: str
    rent: float
    marketing_fee: float
    utilities: float
    ai_token_cost: float
    other_costs: float
    total_cost: float
    total: float
    note: Optional[str] = None
    attachments: list[Any] = Field(default_factory=list)
    locked: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExpenseSummaryResponse(BaseModel):
    """费用汇总响应"""

    year_month: str
    shop_count: int
    total_rent: float
    total_marketing_fee: float
    total_utilities: float
    total_ai_token_cost: float
    total_other_costs: float
    total_amount: float
