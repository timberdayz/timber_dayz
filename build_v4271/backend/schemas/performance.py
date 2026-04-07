"""
绩效管理 API 契约 (Contract-First)
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PerformanceConfigCreateRequest(BaseModel):
    """创建绩效配置请求"""

    config_name: str = Field("default", description="配置名称")
    sales_weight: int = Field(30, ge=0, le=100, description="销售额权重(%)")
    profit_weight: int = Field(25, ge=0, le=100, description="毛利权重(%)")
    key_product_weight: int = Field(
        25, ge=0, le=100, description="重点产品权重(%)"
    )
    operation_weight: int = Field(20, ge=0, le=100, description="运营权重(%)")
    sales_max_score: int = Field(
        30, ge=0, le=100, description="销售额满分(达成率>100%得满分)"
    )
    profit_max_score: int = Field(25, ge=0, le=100, description="毛利满分")
    key_product_max_score: int = Field(
        25, ge=0, le=100, description="重点产品满分"
    )
    operation_max_score: int = Field(20, ge=0, le=100, description="运营满分")
    effective_from: date = Field(..., description="生效开始日期")
    effective_to: Optional[date] = Field(None, description="生效结束日期")


class PerformanceConfigUpdateRequest(BaseModel):
    """更新绩效配置请求"""

    config_name: Optional[str] = None
    sales_weight: Optional[int] = Field(None, ge=0, le=100)
    profit_weight: Optional[int] = Field(None, ge=0, le=100)
    key_product_weight: Optional[int] = Field(None, ge=0, le=100)
    operation_weight: Optional[int] = Field(None, ge=0, le=100)
    sales_max_score: Optional[int] = Field(None, ge=0, le=100)
    profit_max_score: Optional[int] = Field(None, ge=0, le=100)
    key_product_max_score: Optional[int] = Field(None, ge=0, le=100)
    operation_max_score: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PerformanceConfigResponse(BaseModel):
    """绩效配置响应"""

    id: int
    config_name: str
    sales_weight: int
    profit_weight: int
    key_product_weight: int
    operation_weight: int
    sales_max_score: int = 30
    profit_max_score: int = 25
    key_product_max_score: int = 25
    operation_max_score: int = 20
    is_active: bool
    effective_from: date
    effective_to: Optional[date]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PerformanceScoreResponse(BaseModel):
    """绩效评分响应"""

    id: int
    platform_code: str
    shop_id: str
    shop_name: Optional[str] = None
    period: str
    total_score: float
    sales_score: float
    profit_score: float
    key_product_score: float
    operation_score: float
    rank: Optional[int]
    performance_coefficient: float

    class Config:
        from_attributes = True
