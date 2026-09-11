from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


_CODE_PATTERN = r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"
_CATEGORY_CODE_PATTERN = r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$"


class ProductCategoryCreateRequest(BaseModel):
    category_code: str = Field(min_length=1, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    parent_category_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    level: int = Field(ge=1, le=2)
    name_zh: str = Field(min_length=1, max_length=128)
    name_en: Optional[str] = Field(default=None, max_length=128)
    category_path: Optional[str] = Field(default=None, max_length=512)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    version: str = Field(default="v1", min_length=1, max_length=32)
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_parent_by_level(self):
        if self.level == 1 and self.parent_category_code is not None:
            raise ValueError("level 1 category cannot have a parent")
        if self.level == 2 and not self.parent_category_code:
            raise ValueError("level 2 category requires a parent category")
        return self


class ProductCategoryUpdateRequest(BaseModel):
    name_zh: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name_en: Optional[str] = Field(default=None, max_length=128)
    category_path: Optional[str] = Field(default=None, max_length=512)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    effective_to: Optional[date] = None
    description: Optional[str] = None


class ProductCategoryResponse(ProductCategoryCreateRequest):
    model_config = {"from_attributes": True}


class SpuBulkItem(BaseModel):
    spu: str = Field(min_length=1, max_length=128, pattern=_CODE_PATTERN)
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l2: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    category_l2_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    biz_status: Optional[str] = Field(default=None, pattern=r"^(candidate|testing|promoted|retired)$")
    owner_user_id: Optional[int] = None
    active: Optional[bool] = None


class SpuBulkRequest(BaseModel):
    items: list[SpuBulkItem] = Field(default_factory=list)


class SkuBulkItem(BaseModel):
    sku_id: Optional[int] = Field(default=None, gt=0)
    sku_key: str = Field(min_length=1, max_length=255)
    erp_record_id: Optional[str] = None
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, ge=0)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: Optional[str] = Field(default="CNY", min_length=3, max_length=8)
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: Optional[str] = Field(default="low", pattern=r"^(low|medium|high)$")


class SkuBulkRequest(BaseModel):
    items: list[SkuBulkItem] = Field(default_factory=list)


class SpuCreateRequest(BaseModel):
    spu: str = Field(min_length=1, max_length=128, pattern=_CODE_PATTERN)
    spu_name: str = Field(min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    category_l2_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    main_image_url: Optional[str] = None
    biz_status: str = Field(default="candidate", pattern=r"^(candidate|testing|promoted|retired)$")
    owner_user_id: Optional[int] = None


class SpuUpdateRequest(BaseModel):
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    category_l2_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    main_image_url: Optional[str] = None
    biz_status: Optional[str] = Field(default=None, pattern=r"^(candidate|testing|promoted|retired)$")
    owner_user_id: Optional[int] = None
    active: Optional[bool] = None


class SkuCreateRequest(BaseModel):
    sku_key: str = Field(min_length=1, max_length=255)
    erp_record_id: Optional[str] = None
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, ge=0)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: str = Field(default="CNY", min_length=3, max_length=8)
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: str = Field(default="low", pattern=r"^(low|medium|high)$")


class SkuUpdateRequest(BaseModel):
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, ge=0)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: Optional[str] = Field(default=None, pattern=r"^(low|medium|high)$")
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")


class SpuSkuBindingRequest(BaseModel):
    sku_id: int = Field(gt=0)
    effective_from: date


class ProductCenterItem(BaseModel):
    model_config = {"from_attributes": True}

    spu: Optional[str] = None
    spu_name: Optional[str] = None
    sku_id: Optional[int] = None
    sku_key: Optional[str] = None
    sku_name: Optional[str] = None
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = None
    category_l2_code: Optional[str] = None
    biz_status: Optional[str] = None
    owner_user_id: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    binding_status: Optional[str] = None
    weight_kg: Optional[float] = None
    package_length_cm: Optional[float] = None
    package_width_cm: Optional[float] = None
    package_height_cm: Optional[float] = None
    units_per_carton: Optional[int] = None
    status: Optional[str] = None
    default_purchase_cost: Optional[float] = None
    purchase_cost_currency: Optional[str] = None
    purchase_cost_source: Optional[str] = None
    purchase_cost_confidence: Optional[str] = None
    updated_at: Optional[datetime] = None


class ProductCenterListResponse(BaseModel):
    data: list[ProductCenterItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProductCenterBindingResponse(BaseModel):
    id: int
    spu: str
    sku_id: int
    effective_from: date
    effective_to: Optional[date]
    binding_status: str


class CostAssumptionCreateRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    destination: Optional[str] = None
    transport_type: Optional[str] = None
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity)$")
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    customs_rate: Optional[float] = Field(default=None, ge=0)
    storage_unit_rate: Optional[float] = Field(default=None, ge=0)
    platform_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_rate: Optional[float] = Field(default=None, ge=0, le=1)
    damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    effective_from: date
    effective_to: Optional[date] = None
    assumption_source: Optional[str] = None
    confidence_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")


class CostAssumptionUpdateRequest(BaseModel):
    profile_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    destination: Optional[str] = None
    transport_type: Optional[str] = None
    billing_basis: Optional[str] = Field(default=None, pattern=r"^(volume|weight|quantity)$")
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    customs_rate: Optional[float] = Field(default=None, ge=0)
    storage_unit_rate: Optional[float] = Field(default=None, ge=0)
    platform_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_rate: Optional[float] = Field(default=None, ge=0, le=1)
    damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    assumption_source: Optional[str] = None
    confidence_level: Optional[str] = Field(default=None, pattern=r"^(low|medium|high)$")
    active: Optional[bool] = None


class LogisticsBillCreateRequest(BaseModel):
    bill_no: str = Field(min_length=1, max_length=128)
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: date
    transport_type: Optional[str] = Field(default=None, max_length=64)
    destination: Optional[str] = Field(default=None, max_length=128)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    total_amount: float = Field(ge=0)
    notes: Optional[str] = None


class LogisticsBillUpdateRequest(BaseModel):
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: Optional[date] = None
    transport_type: Optional[str] = Field(default=None, max_length=64)
    destination: Optional[str] = Field(default=None, max_length=128)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    total_amount: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


class LogisticsBillSkuLineRequest(BaseModel):
    sku_id: int = Field(gt=0)
    shipped_qty: float = Field(gt=0)
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None


class LogisticsBillLineRequest(BaseModel):
    """Provider statement row; supports one or many SKU allocations."""

    sku_ids: list[int] = Field(min_length=1)
    po_id: Optional[str] = Field(default=None, max_length=64)
    shipped_qty: float = Field(default=0, ge=0)
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity|fixed)$")
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    billing_unit_rate: Optional[float] = Field(default=None, ge=0)
    line_total_amount: float = Field(default=0, ge=0)
    is_sensitive: bool = False
    sensitive_surcharge: float = Field(default=0, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None


class LogisticsBillLinesReplaceRequest(BaseModel):
    lines: list[LogisticsBillLineRequest | LogisticsBillSkuLineRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_skus(self):
        # Legacy one-SKU rows remain accepted; new rows may contain multiple SKUs.
        legacy_ids = [line.sku_id for line in self.lines if isinstance(line, LogisticsBillSkuLineRequest)]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise ValueError("a logistics bill can contain each SKU only once")
        return self


class LogisticsBillPurchaseOrdersReplaceRequest(BaseModel):
    po_ids: list[str] = Field(min_length=1)


class LogisticsProviderRuleCreateRequest(BaseModel):
    logistics_provider: str = Field(min_length=1, max_length=128)
    destination: Optional[str] = Field(default=None, max_length=128)
    transport_type: Optional[str] = Field(default=None, max_length=64)
    cargo_class: Optional[str] = Field(default=None, max_length=64)
    is_sensitive: bool = False
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity|fixed)$")
    billing_unit: str = Field(default="RMB/CBM", max_length=32)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    sensitive_surcharge_mode: str = Field(default="manual", max_length=32)
    sensitive_surcharge_rate: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None


class LogisticsProviderRuleUpdateRequest(LogisticsProviderRuleCreateRequest):
    logistics_provider: Optional[str] = Field(default=None, min_length=1, max_length=128)
    effective_from: Optional[date] = None


class LogisticsBillVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class ProfitPreviewRequest(BaseModel):
    sku_id: int = Field(gt=0)
    selling_price: float = Field(ge=0)
    coupon_amount: float = Field(default=0, ge=0)
    destination: Optional[str] = None
    transport_type: Optional[str] = None


class ProfitEstimateSaveRequest(ProfitPreviewRequest):
    assumption_version: str = Field(min_length=1, max_length=64)


class FeishuProjectionInitializeRequest(BaseModel):
    spu_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sku_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)


class ProfitEstimateCreateRequest(BaseModel):
    sku_id: int = Field(gt=0)
    assumption_version: str = Field(min_length=1, max_length=64)
    scenario: str = Field(default="base", pattern=r"^base$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    coupon_amount: Optional[float] = Field(default=None, ge=0)
    purchase_cost: Optional[float] = Field(default=None, ge=0)
    logistics_cost: Optional[float] = Field(default=None, ge=0)
    storage_cost: Optional[float] = Field(default=None, ge=0)
    platform_fee: Optional[float] = Field(default=None, ge=0)
    expected_return_loss: Optional[float] = Field(default=None, ge=0)
    expected_damage_loss: Optional[float] = Field(default=None, ge=0)
    cost_completeness: str = Field(default="incomplete", pattern=r"^(complete|partial|incomplete)$")
    confidence_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")
