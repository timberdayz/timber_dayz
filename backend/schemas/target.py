"""
目标管理 API 契约 (Contract-First)
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TargetCreateRequest(BaseModel):
    """创建目标请求"""

    target_name: str = Field(..., description="目标名称")
    target_type: str = Field(
        ..., description="目标类型:shop/product/campaign"
    )
    period_start: date = Field(..., description="开始时间")
    period_end: date = Field(..., description="结束时间")
    target_amount: float = Field(0.0, ge=0, description="目标销售额(CNY)")
    target_quantity: int = Field(0, ge=0, description="目标订单数/销量")
    description: Optional[str] = Field(None, description="目标描述")


class TargetUpdateRequest(BaseModel):
    """更新目标请求"""

    target_name: Optional[str] = None
    target_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    target_amount: Optional[float] = Field(None, ge=0)
    target_quantity: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    description: Optional[str] = None
    weekday_ratios: Optional[Dict[str, float]] = Field(
        None,
        description="周一到周日拆分比例 {\"1\":0.14,...,\"7\":0.14} 和为1",
    )


class BreakdownCreateRequest(BaseModel):
    """创建目标分解请求"""

    breakdown_type: str = Field(..., description="分解类型:shop/time")
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_label: Optional[str] = None
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)


class GenerateDailyBreakdownRequest(BaseModel):
    """一键生成日度分解请求"""

    overwrite: bool = Field(False, description="是否覆盖已存在的日度分解")
    weekday_ratios: Optional[Dict[str, float]] = Field(
        None,
        description="周一到周日拆分比例 1=周一...7=周日，和为1；不传则用目标已保存的",
    )


class TargetResponse(BaseModel):
    """目标响应"""

    id: int
    target_name: str
    target_type: str
    period_start: date
    period_end: date
    target_amount: float
    target_quantity: int
    achieved_amount: float
    achieved_quantity: int
    achievement_rate: float
    status: str
    description: Optional[str]
    weekday_ratios: Optional[Dict[str, float]] = None
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BreakdownResponse(BaseModel):
    """目标分解响应"""

    id: int
    target_id: int
    breakdown_type: str
    platform_code: Optional[str]
    shop_id: Optional[str]
    shop_name: Optional[str] = None
    period_start: Optional[date]
    period_end: Optional[date]
    period_label: Optional[str]
    target_amount: float
    target_quantity: int
    achieved_amount: float
    achieved_quantity: int
    achievement_rate: float

    class Config:
        from_attributes = True
