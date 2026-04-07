"""
目标管理 API 合约
"""

from datetime import date, datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class TargetCreateRequest(BaseModel):
    target_name: str = Field(..., description="目标名称")
    target_type: str = Field(..., description="目标类型: shop/product/campaign/operation")
    period_start: date = Field(..., description="开始日期")
    period_end: date = Field(..., description="结束日期")
    target_amount: float = Field(0.0, ge=0, description="目标销售额(CNY)")
    target_quantity: int = Field(0, ge=0, description="目标数量")
    target_profit_amount: float = Field(0.0, ge=0, description="目标毛利(CNY)")
    achieved_profit_amount: float = Field(0.0, ge=0, description="实际毛利(CNY)")
    product_id: Optional[int] = Field(None, description="产品ID")
    platform_sku: Optional[str] = Field(None, description="平台SKU")
    company_sku: Optional[str] = Field(None, description="公司SKU")
    metric_code: Optional[str] = Field(None, description="运营指标编码")
    metric_name: Optional[str] = Field(None, description="运营指标名称")
    metric_direction: Optional[str] = Field(
        None,
        description="指标方向: higher_better/lower_better/manual_score",
    )
    target_value: Optional[float] = Field(None, description="运营指标目标值")
    achieved_value: Optional[float] = Field(None, description="运营指标实际值")
    max_score: Optional[float] = Field(None, ge=0, description="指标满分")
    penalty_enabled: bool = Field(False, description="是否启用罚分")
    penalty_threshold: Optional[float] = Field(None, description="罚分阈值")
    penalty_per_unit: Optional[float] = Field(None, description="每超出一单位罚分")
    penalty_max: Optional[float] = Field(None, description="最大罚分")
    manual_score_enabled: bool = Field(False, description="是否允许人工打分")
    manual_score_value: Optional[float] = Field(None, description="人工打分值")
    description: Optional[str] = Field(None, description="目标描述")


class TargetUpdateRequest(BaseModel):
    target_name: Optional[str] = None
    target_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    target_amount: Optional[float] = Field(None, ge=0)
    target_quantity: Optional[int] = Field(None, ge=0)
    target_profit_amount: Optional[float] = Field(None, ge=0)
    achieved_profit_amount: Optional[float] = Field(None, ge=0)
    product_id: Optional[int] = None
    platform_sku: Optional[str] = None
    company_sku: Optional[str] = None
    metric_code: Optional[str] = None
    metric_name: Optional[str] = None
    metric_direction: Optional[str] = None
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    max_score: Optional[float] = Field(None, ge=0)
    penalty_enabled: Optional[bool] = None
    penalty_threshold: Optional[float] = None
    penalty_per_unit: Optional[float] = None
    penalty_max: Optional[float] = None
    manual_score_enabled: Optional[bool] = None
    manual_score_value: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None
    weekday_ratios: Optional[Dict[str, float]] = Field(
        None,
        description='周一到周日拆分比例 {"1":0.14,...,"7":0.14} 和为1',
    )


class BreakdownCreateRequest(BaseModel):
    breakdown_type: str = Field(..., description="分解类型: shop/time")
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_label: Optional[str] = None
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)
    target_profit_amount: float = Field(0.0, ge=0)
    achieved_profit_amount: float = Field(0.0, ge=0)
    product_id: Optional[int] = None
    platform_sku: Optional[str] = None
    company_sku: Optional[str] = None
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    manual_score_value: Optional[float] = None


class GenerateDailyBreakdownRequest(BaseModel):
    overwrite: bool = Field(False, description="是否覆盖已存在的日度分解")
    weekday_ratios: Optional[Dict[str, float]] = Field(
        None,
        description='周一到周日拆分比例 1=周一...7=周日, 和为1; 不传则用目标已保存的',
    )


class TargetResponse(BaseModel):
    id: int
    target_name: str
    target_type: str
    period_start: date
    period_end: date
    target_amount: float
    target_quantity: int
    target_profit_amount: float
    achieved_amount: float
    achieved_quantity: int
    achieved_profit_amount: float
    product_id: Optional[int] = None
    platform_sku: Optional[str] = None
    company_sku: Optional[str] = None
    achievement_rate: float
    metric_code: Optional[str] = None
    metric_name: Optional[str] = None
    metric_direction: Optional[str] = None
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    max_score: Optional[float] = None
    penalty_enabled: bool = False
    penalty_threshold: Optional[float] = None
    penalty_per_unit: Optional[float] = None
    penalty_max: Optional[float] = None
    manual_score_enabled: bool = False
    manual_score_value: Optional[float] = None
    status: str
    description: Optional[str]
    weekday_ratios: Optional[Dict[str, float]] = None
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BreakdownResponse(BaseModel):
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
    target_profit_amount: float
    achieved_amount: float
    achieved_quantity: int
    achieved_profit_amount: float
    product_id: Optional[int] = None
    platform_sku: Optional[str] = None
    company_sku: Optional[str] = None
    achievement_rate: float
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    manual_score_value: Optional[float] = None

    class Config:
        from_attributes = True
