from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    is_selectable: bool = True
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
    is_selectable: Optional[bool] = None
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
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)
    active: Optional[bool] = None


class SpuBulkRequest(BaseModel):
    items: list[SpuBulkItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_single_spu_request_models(cls, value):
        if not isinstance(value, dict):
            return value
        items = value.get("items")
        if items is None:
            return value
        return {
            **value,
            "items": [
                item.model_dump(exclude_unset=True)
                if isinstance(item, BaseModel)
                else item
                for item in items
            ],
        }


class SkuBulkItem(BaseModel):
    sku_id: Optional[int] = Field(default=None, gt=0)
    sku_key: str = Field(min_length=1, max_length=255)
    spu: Optional[str] = Field(default=None, max_length=128, pattern=_CODE_PATTERN)
    effective_from: Optional[date] = None
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
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    selling_price_source: Optional[str] = Field(default=None, max_length=64)
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency != "CNY" or self.selling_price_currency not in (None, "CNY"):
            raise ValueError("SKU product-center amounts must use CNY")
        return self


class SkuBulkRequest(BaseModel):
    items: list[SkuBulkItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_single_sku_request_models(cls, value):
        if not isinstance(value, dict):
            return value
        items = value.get("items")
        if items is None:
            return value
        return {
            **value,
            "items": [
                item.model_dump(exclude_unset=True)
                if isinstance(item, BaseModel)
                else item
                for item in items
            ],
        }


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
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)


class SpuUpdateRequest(BaseModel):
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    category_l2_code: Optional[str] = Field(default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN)
    main_image_url: Optional[str] = None
    biz_status: Optional[str] = Field(default=None, pattern=r"^(candidate|testing|promoted|retired)$")
    owner_user_id: Optional[int] = None
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)
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
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: str = Field(default="CNY", min_length=3, max_length=8)
    selling_price_source: Optional[str] = Field(default=None, max_length=64)
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency != "CNY" or self.selling_price_currency != "CNY":
            raise ValueError("SKU product-center amounts must use CNY")
        return self


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
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    selling_price_source: Optional[str] = Field(default=None, max_length=64)
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency not in (None, "CNY") or self.selling_price_currency not in (None, "CNY"):
            raise ValueError("SKU product-center amounts must use CNY")
        return self
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
    purchase_cost_confirmed_at: Optional[datetime] = None
    expected_logistics_cost: Optional[float] = None
    expected_storage_cost: Optional[float] = None
    reference_selling_price: Optional[float] = None
    selling_price_currency: Optional[str] = None
    selling_price_source: Optional[str] = None
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = None
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    actual_storage_cost: Optional[float] = None
    data_completeness: Optional[str] = None
    updated_at: Optional[datetime] = None


class ProductCenterListResponse(BaseModel):
    data: list[ProductCenterItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class BulkMutationResponse(BaseModel):
    created: int
    updated: int
    items: list[ProductCenterItem]


class ProductCenterBindingResponse(BaseModel):
    id: int
    spu: str
    sku_id: int
    effective_from: date
    effective_to: Optional[date]
    binding_status: str


class ProductWarehouseCreateRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=128)
    warehouse_name: str = Field(min_length=1, max_length=256)
    country_code: str = Field(min_length=2, max_length=16)
    country_name: str = Field(min_length=1, max_length=64)
    region: Optional[str] = Field(default=None, max_length=64)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None


class ProductWarehouseUpdateRequest(BaseModel):
    warehouse_name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=16)
    country_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    region: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PlatformFeeRateUpdateRequest(BaseModel):
    default_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    fee_rate_effective_from: date = Field(default_factory=date.today)
    fee_rate_source: Optional[str] = Field(default=None, max_length=128)
    fee_rate_version: Optional[str] = Field(default=None, max_length=64)


class WarehouseStorageRuleCreateRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=128)
    unit_rate_cny: float = Field(ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class WarehouseStorageRuleUpdateRequest(BaseModel):
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None


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


_LOGISTICS_BILLING_UNITS = {
    "volume": "CNY/CBM",
    "weight": "CNY/KG",
    "quantity": "CNY/unit",
    "fixed": "CNY",
}


class LogisticsBillCreateRequest(BaseModel):
    bill_no: str = Field(min_length=1, max_length=128)
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: date
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    total_amount: float = Field(ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency != "CNY":
            raise ValueError("product-center logistics bills must use CNY")
        return self


class LogisticsBillUpdateRequest(BaseModel):
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: Optional[date] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    total_amount: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency is not None and self.currency != "CNY":
            raise ValueError("product-center logistics bills must use CNY")
        return self


class LogisticsBillSkuLineRequest(BaseModel):
    """Compatibility request for legacy one-SKU bill rows.

    Legacy rows were always volume-billed.  Keep that contract explicit so a
    request cannot reach persistence without a canonical CNY billing unit.
    """

    sku_id: int = Field(gt=0)
    warehouse_code: str = Field(min_length=1, max_length=128)
    shipped_qty: float = Field(gt=0)
    billing_basis: Literal["volume"] = "volume"
    billing_unit: Literal["CNY/CBM"] = "CNY/CBM"
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None


class LogisticsBillLineAllocationRequest(BaseModel):
    """A single purchase-order SKU share of a provider statement row."""

    sku_id: int = Field(gt=0)
    po_id: Optional[str] = Field(default=None, max_length=64)
    shipped_qty: float = Field(gt=0)


class LogisticsBillLineRequest(BaseModel):
    """Provider statement row; supports one or many SKU allocations."""

    sku_ids: list[int] = Field(min_length=1)
    allocations: list[LogisticsBillLineAllocationRequest] = Field(default_factory=list)
    po_id: Optional[str] = Field(default=None, max_length=64)
    warehouse_code: str = Field(min_length=1, max_length=128)
    shipped_qty: float = Field(default=0, ge=0)
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity|fixed)$")
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    billing_unit_rate: Optional[float] = Field(default=None, ge=0)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    line_total_amount: float = Field(default=0, ge=0)
    is_sensitive: bool = False
    sensitive_surcharge: float = Field(default=0, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def normalize_legacy_rate(self):
        if self.billing_unit_rate is None and self.freight_unit_rate is not None:
            self.billing_unit_rate = self.freight_unit_rate
        return self

    @model_validator(mode="after")
    def derive_cny_billing_unit(self):
        expected_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        if self.billing_unit is not None and self.billing_unit != expected_unit:
            raise ValueError(f"billing_unit must be {expected_unit}; product-center logistics costs use CNY")
        self.billing_unit = expected_unit
        return self

    @model_validator(mode="after")
    def validate_allocation_skus(self):
        if not self.allocations:
            return self
        allocation_sku_ids = [item.sku_id for item in self.allocations]
        if len(allocation_sku_ids) != len(set(allocation_sku_ids)):
            raise ValueError("a statement row can contain a SKU only once")
        if set(allocation_sku_ids) != set(self.sku_ids):
            raise ValueError("allocation SKU IDs must match sku_ids")
        return self


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


class PurchaseOrderLineCostSupplementRequest(BaseModel):
    """Manual cost completion when an imported purchase order has no amount."""

    unit_price: float = Field(ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    purchase_cost_source: str = Field(default="manual", min_length=1, max_length=64)

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency not in (None, "CNY"):
            raise ValueError("purchase-order product-center costs must use CNY")
        return self


class LogisticsProviderRuleCreateRequest(BaseModel):
    logistics_provider: str = Field(min_length=1, max_length=128)
    warehouse_code: Optional[str] = Field(default=None, max_length=128)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    cargo_class: Optional[str] = Field(default=None, max_length=64)
    is_sensitive: bool = False
    is_default: bool = False
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity|fixed)$")
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    sensitive_surcharge_mode: str = Field(default="manual", max_length=32)
    sensitive_surcharge_rate: Optional[float] = Field(default=None, ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def derive_cny_billing_unit(self):
        expected_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        if self.billing_unit is not None and self.billing_unit != expected_unit:
            raise ValueError(f"billing_unit must be {expected_unit}; product-center logistics costs use CNY")
        self.billing_unit = expected_unit
        return self


class LogisticsProviderRuleUpdateRequest(BaseModel):
    """Partial provider-rule update; never inherit create defaults into PATCHes."""

    logistics_provider: Optional[str] = Field(default=None, min_length=1, max_length=128)
    warehouse_code: Optional[str] = Field(default=None, max_length=128)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    cargo_class: Optional[str] = Field(default=None, max_length=64)
    is_sensitive: Optional[bool] = None
    is_default: Optional[bool] = None
    billing_basis: Optional[str] = Field(default=None, pattern=r"^(volume|weight|quantity|fixed)$")
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    sensitive_surcharge_mode: Optional[str] = Field(default=None, max_length=32)
    sensitive_surcharge_rate: Optional[float] = Field(default=None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def derive_cny_billing_unit_when_basis_changes(self):
        if "billing_unit" in self.model_fields_set:
            raise ValueError("billing_unit is derived from billing_basis")
        if self.billing_basis is not None:
            self.billing_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        return self


class LogisticsBillVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class ProfitPreviewRequest(BaseModel):
    sku_id: int = Field(gt=0)
    platform_code: Optional[str] = Field(default=None, max_length=32)
    selling_price: float = Field(ge=0)
    coupon_amount: float = Field(default=0, ge=0)
    warehouse_code: Optional[str] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")


class SkuOperatingProfileCreateRequest(BaseModel):
    sku_id: int = Field(gt=0)
    platform_code: str = Field(min_length=1, max_length=32)
    warehouse_code: str = Field(min_length=1, max_length=128)
    warehouse_name: Optional[str] = Field(default=None, max_length=256)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    default_coupon_amount: Optional[float] = Field(default=None, ge=0)
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None


class SkuOperatingProfileUpdateRequest(BaseModel):
    warehouse_name: Optional[str] = Field(default=None, max_length=256)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    default_coupon_amount: Optional[float] = Field(default=None, ge=0)
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class SkuOperatingProfileBulkRequest(BaseModel):
    items: list[SkuOperatingProfileCreateRequest] = Field(default_factory=list)


class SkuOperatingProfileResponse(SkuOperatingProfileCreateRequest):
    profile_id: Optional[int] = None
    platform_fee_rate: Optional[float] = None
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    sku_key: Optional[str] = None
    sku_name: Optional[str] = None
    spu: Optional[str] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    purchase_cost: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    actual_storage_cost: Optional[float] = None
    cost_completeness: Optional[str] = None
    confidence_level: Optional[str] = None
    latest_estimate_as_of: Optional[datetime] = None
    latest_estimate_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SkuOperatingProfitRequest(BaseModel):
    selling_price: Optional[float] = Field(default=None, ge=0)
    coupon_amount: Optional[float] = Field(default=None, ge=0)
    warehouse_code: Optional[str] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class SkuOperatingPlatformOption(BaseModel):
    platform_code: str
    name: Optional[str] = None
    default_fee_rate: Optional[float] = None
    fee_rate_effective_from: Optional[date] = None
    fee_rate_source: Optional[str] = None
    fee_rate_version: Optional[str] = None


class SkuOperatingDimensionsResponse(BaseModel):
    platforms: list[SkuOperatingPlatformOption]
    spus: list[str] = []
    skus: list[dict] = []
    warehouses: list[dict]


class SkuOperatingProfitResponse(BaseModel):
    sku_id: int
    profile_id: int
    platform_code: str
    warehouse_code: str
    net_revenue: Optional[float] = None
    purchase_cost: Optional[float] = None
    logistics_cost: Optional[float] = None
    storage_cost: Optional[float] = None
    platform_fee: Optional[float] = None
    expected_return_loss: Optional[float] = None
    expected_damage_loss: Optional[float] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    logistics_cost_source: Optional[str] = None
    storage_cost_source: Optional[str] = None
    cost_completeness: Optional[str] = None
    confidence_level: Optional[str] = None


class SkuOperatingProfitSaveResponse(BaseModel):
    estimate_id: int
    profile_id: int
    sku_id: int
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None


class SkuOperatingProfitHistoryResponse(BaseModel):
    estimate_id: int
    profile_id: int
    sku_id: int
    platform_code: Optional[str] = None
    warehouse_code: Optional[str] = None
    estimate_as_of: Optional[datetime] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    cost_completeness: str
    confidence_level: str


class PlatformSkuProfitPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: int = Field(gt=0)
    platform_code: str = Field(min_length=1, max_length=32)
    warehouse_code: str = Field(min_length=1, max_length=128)
    transport_type: str = Field(pattern=r"^(sea|air|rail)$")
    competitor_price: Optional[float] = Field(default=None, ge=0)
    expected_selling_price: Optional[float] = Field(default=None, ge=0)
    seller_coupon_amount: float = Field(default=0, ge=0)
    expected_ad_rate: float = Field(default=0, ge=0, le=1)


class PlatformSkuProfitEstimateRequest(PlatformSkuProfitPreviewRequest):
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class PlatformSkuProfitCandidateResponse(BaseModel):
    sku_id: int
    sku_key: str
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    spu: Optional[str] = None
    reference_selling_price: Optional[float] = None
    purchase_cost: Optional[float] = None
    platform_code: str
    warehouse_code: str
    transport_type: str
    expected_selling_price: Optional[float] = None
    competitor_price: Optional[float] = None
    seller_coupon_amount: Optional[float] = None
    expected_ad_rate: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    actual_storage_cost: Optional[float] = None
    platform_fee_rate: Optional[float] = None
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    configuration_status: str
    turnover_class: Optional[str] = None
    reference_storage_days: Optional[int] = None
    reference_logistics_cost: Optional[float] = None
    reference_storage_cost: Optional[float] = None
    preview: Optional[dict] = None
    currency: str = "CNY"


class PlatformSkuProfitCandidatePageResponse(BaseModel):
    data: list[PlatformSkuProfitCandidateResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProfitEstimateSaveRequest(ProfitPreviewRequest):
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class FeishuProjectionInitializeRequest(BaseModel):
    spu_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sku_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    platform_sku_profit_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)


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
