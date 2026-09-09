from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SpuCreateRequest(BaseModel):
    spu: str = Field(min_length=1, max_length=128)
    spu_name: str = Field(min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    main_image_url: Optional[str] = None
    biz_status: str = Field(default="candidate", pattern=r"^(candidate|testing|promoted|retired)$")
    owner_user_id: Optional[int] = None


class SpuUpdateRequest(BaseModel):
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
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


class SkuUpdateRequest(BaseModel):
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, ge=0)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
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
    return_rate: Optional[float] = Field(default=None, ge=0, le=1)
    damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    effective_from: date
    effective_to: Optional[date] = None
    assumption_source: Optional[str] = None
    confidence_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")


class ProfitEstimateCreateRequest(BaseModel):
    sku_id: int = Field(gt=0)
    assumption_version: str = Field(min_length=1, max_length=64)
    scenario: str = Field(default="base", pattern=r"^(base|conservative|optimistic)$")
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
