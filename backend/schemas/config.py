"""
配置管理相关 API 契约 (Contract-First)

从 `backend/routers/config_management.py` 提取的 Pydantic 模型：
- SalesTargetCreate / SalesTargetUpdate / SalesTargetResponse
- CampaignTargetCreate / CampaignTargetUpdate / CampaignTargetResponse
"""

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field
from uuid import UUID


class SalesTargetCreate(BaseModel):
    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(
        ..., description="目标月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"
    )
    target_sales_amount: float = Field(..., ge=0, description="目标销售额")
    target_order_count: int = Field(..., ge=0, description="目标订单数")


class SalesTargetUpdate(BaseModel):
    target_sales_amount: Optional[float] = Field(None, ge=0)
    target_order_count: Optional[int] = Field(None, ge=0)


class SalesTargetResponse(BaseModel):
    id: int
    shop_id: str
    year_month: str
    target_sales_amount: float
    target_order_count: int
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class CampaignTargetCreate(BaseModel):
    platform_code: str = Field(..., description="平台代码")
    campaign_name: str = Field(..., description="战役名称")
    campaign_type: Optional[str] = Field(None, description="战役类型")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    target_gmv: float = Field(..., ge=0, description="目标GMV")
    target_roi: Optional[float] = Field(None, ge=0, description="目标ROI")
    budget_amount: Optional[float] = Field(None, ge=0, description="预算金额")


class CampaignTargetUpdate(BaseModel):
    campaign_name: Optional[str] = None
    campaign_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_gmv: Optional[float] = Field(None, ge=0)
    target_roi: Optional[float] = Field(None, ge=0)
    budget_amount: Optional[float] = Field(None, ge=0)


class CampaignTargetResponse(BaseModel):
    id: UUID
    platform_code: str
    campaign_name: str
    campaign_type: Optional[str]
    start_date: date
    end_date: date
    target_gmv: float
    target_roi: Optional[float]
    budget_amount: Optional[float]
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


__all__ = [
    "SalesTargetCreate",
    "SalesTargetUpdate",
    "SalesTargetResponse",
    "CampaignTargetCreate",
    "CampaignTargetUpdate",
    "CampaignTargetResponse",
]

