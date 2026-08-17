"""
目标管理 API 契约。
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TargetCreateRequest(BaseModel):
    target_name: str = Field(..., description="目标名称")
    target_type: str = Field(
        ..., description="目标类型: shop/product/campaign/operation"
    )
    scope_type: Optional[str] = Field(None, description="作用域类型: shop/employee")
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
    scope_type: Optional[str] = None
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
        description="周一到周日拆分比例 1=周一...7=周日, 和为1; 不传则用目标已保存的",
    )


class TargetResponse(BaseModel):
    id: int
    target_name: str
    target_type: str
    scope_type: Optional[str] = None
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


class ShopTargetWorkbenchShopInput(BaseModel):
    platform_code: str
    shop_id: str
    ratio: float = Field(0.0, ge=0)
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)
    target_profit_basis_amount: float = Field(0.0, ge=0)


class ShopTargetWorkbenchApplyRequest(BaseModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    company_target_amount: float = Field(0.0, ge=0)
    company_target_quantity: int = Field(0, ge=0)
    company_target_profit_basis_amount: float = Field(0.0, ge=0)
    weekday_ratios: Dict[str, float] = Field(default_factory=dict)
    shops: List[ShopTargetWorkbenchShopInput] = Field(default_factory=list)


class ShopTargetWorkbenchShopResponse(BaseModel):
    platform_code: str
    shop_id: str
    standard_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    ratio: float = 0.0
    target_amount: float = 0.0
    target_quantity: int = 0
    target_profit_basis_amount: float = 0.0
    daily_target_count: int = 0


class ShopTargetWorkbenchResponse(BaseModel):
    year_month: str
    target_id: Optional[int] = None
    company_target_amount: float = 0.0
    company_target_quantity: int = 0
    company_target_profit_basis_amount: float = 0.0
    weekday_ratios: Dict[str, float] = Field(default_factory=dict)
    shops: List[ShopTargetWorkbenchShopResponse] = Field(default_factory=list)


class ShopTargetWorkbenchApplyResponse(BaseModel):
    year_month: str
    target_id: int
    synced: int = 0
    errors: List[str] = Field(default_factory=list)


class OperationWorkbenchMetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str
    is_enabled: bool = True


class OperationWorkbenchShopOverrideInput(BaseModel):
    metric_code: str
    platform_code: str
    shop_id: str
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    manual_score_value: Optional[float] = None


class OperationWorkbenchApplyRequest(BaseModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    catalog_version: int = Field(..., ge=1)
    performance_config_id: Optional[int] = None
    expected_performance_config_updated_at: Optional[datetime] = None
    expected_updated_at: Optional[datetime] = None
    metrics: List[OperationWorkbenchMetricInput] = Field(default_factory=list)
    shop_overrides: List[OperationWorkbenchShopOverrideInput] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_unique_operation_keys(self):
        metric_codes = [item.metric_code.strip() for item in self.metrics]
        if len(metric_codes) != len(set(metric_codes)):
            raise ValueError("运营指标不能重复")

        override_keys = [
            (
                item.metric_code.strip(),
                item.platform_code.strip().lower(),
                item.shop_id.strip(),
            )
            for item in self.shop_overrides
        ]
        if len(override_keys) != len(set(override_keys)):
            raise ValueError("店铺覆盖不能重复")
        if self.shop_overrides:
            raise ValueError("店铺数据必须通过店铺录入工作台保存")
        return self


class OperationWorkbenchEntryMetricResponse(BaseModel):
    metric_code: str
    metric_name: Optional[str] = None
    metric_direction: Optional[str] = None
    target_value: Optional[float] = None
    max_score: float = 0
    input_kind: str
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    auto_score: Optional[int] = None
    scoring_detail: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[str] = None
    guidance: Optional[str] = None
    formula: Optional[str] = None
    status: str


class OperationWorkbenchEntryShopResponse(BaseModel):
    platform_code: str
    shop_id: str
    standard_name: str
    aliases: List[str] = Field(default_factory=list)
    status: str
    configuration_errors: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: List[OperationWorkbenchEntryMetricResponse] = Field(default_factory=list)


class OperationWorkbenchEntriesResponse(BaseModel):
    year_month: str
    scope_confirmed: bool
    shops: List[OperationWorkbenchEntryShopResponse] = Field(default_factory=list)
    completion: Dict[str, int] = Field(default_factory=dict)
    configuration_errors: List[Dict[str, Any]] = Field(default_factory=list)


class OperationWorkbenchEntriesApiResponse(BaseModel):
    success: bool = True
    data: OperationWorkbenchEntriesResponse


class OperationWorkbenchScopeShopInput(BaseModel):
    platform_code: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=256)
    is_included: bool = True
    exclusion_reason: Optional[str] = Field(default=None, max_length=512)


class OperationWorkbenchScopeApplyRequest(BaseModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    shops: List[OperationWorkbenchScopeShopInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_shop_keys(self):
        keys = [
            (item.platform_code.strip().lower(), item.shop_id.strip())
            for item in self.shops
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("店铺范围不能重复")
        return self


class OperationWorkbenchEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str = Field(..., min_length=1, max_length=64)
    platform_code: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=256)
    actual_value: Optional[float] = None
    completed_count: Optional[int] = Field(default=None, ge=0)
    required_count: Optional[int] = Field(default=None, ge=0)
    result: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_single_entry_value(self):
        has_numeric = self.actual_value is not None
        has_training = self.completed_count is not None or self.required_count is not None
        has_check = self.result is not None or self.note is not None
        if sum((has_numeric, has_training, has_check)) != 1:
            raise ValueError("每条店铺指标必须且只能填写一种受控录入")
        if has_training and (
            self.completed_count is None or self.required_count is None
        ):
            raise ValueError("培训完成率必须同时填写已完成和应完成人数")
        return self


class OperationWorkbenchEntryApplyRequest(BaseModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    entries: List[OperationWorkbenchEntryInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_entry_keys(self):
        keys = [
            (
                item.metric_code.strip(),
                item.platform_code.strip().lower(),
                item.shop_id.strip(),
            )
            for item in self.entries
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("店铺指标不能重复")
        return self
