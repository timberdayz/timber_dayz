"""
销售战役管理 API 契约 (Contract-First)
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CampaignCreateRequest(BaseModel):
    """创建战役请求"""

    campaign_name: str = Field(..., description="战役名称")
    campaign_type: str = Field(
        ..., description="战役类型:holiday/new_product/special_event"
    )
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    target_amount: float = Field(0.0, ge=0, description="目标销售额(CNY)")
    target_quantity: int = Field(0, ge=0, description="目标订单数/销量")
    description: Optional[str] = Field(None, description="战役描述")
    shop_ids: Optional[List[Dict[str, str]]] = Field(
        None,
        description="参与店铺列表:[{platform_code, shop_id, target_amount, target_quantity}]",
    )


class CampaignUpdateRequest(BaseModel):
    """更新战役请求"""

    campaign_name: Optional[str] = None
    campaign_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_amount: Optional[float] = Field(None, ge=0)
    target_quantity: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    description: Optional[str] = None


class CampaignShopRequest(BaseModel):
    """添加参与店铺请求"""

    platform_code: str
    shop_id: str
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)


class CampaignResponse(BaseModel):
    """战役响应"""

    id: int
    campaign_name: str
    campaign_type: str
    start_date: date
    end_date: date
    target_amount: float
    target_quantity: int
    actual_amount: float
    actual_quantity: int
    achievement_rate: float
    status: str
    description: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignShopResponse(BaseModel):
    """战役店铺响应"""

    id: int
    campaign_id: int
    platform_code: Optional[str]
    shop_id: Optional[str]
    shop_name: Optional[str] = None
    target_amount: float
    target_quantity: int
    actual_amount: float
    actual_quantity: int
    achievement_rate: float
    rank: Optional[int]

    class Config:
        from_attributes = True
