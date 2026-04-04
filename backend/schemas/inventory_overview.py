from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class InventoryOverviewPlatformBreakdownResponse(BaseModel):
    platform: str
    product_count: int
    total_stock: int


class InventoryOverviewProductItemResponse(BaseModel):
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    platform_sku: str
    product_name: Optional[str] = None
    warehouse: Optional[str] = None
    stock: int = 0
    total_stock: int = 0
    available_stock: int = 0
    reserved_stock: int = 0
    in_transit_stock: int = 0
    category: Optional[str] = None
    brand: Optional[str] = None
    price: float = 0.0
    currency: str = "CNY"
    sales_volume: int = 0
    sales_amount: float = 0.0
    page_views: int = 0
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image_count: int = 0
    all_images: List[str] = Field(default_factory=list)
    metric_date: Optional[date] = None
    updated_at: Optional[datetime] = None


class InventoryOverviewProductListResponse(BaseModel):
    data: List[InventoryOverviewProductItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_previous: bool
    has_next: bool


class InventoryOverviewSummaryResponse(BaseModel):
    total_products: int
    total_stock: int
    total_value: float
    low_stock_count: int
    out_of_stock_count: int
    high_risk_sku_count: int = 0
    medium_risk_sku_count: int = 0
    low_risk_sku_count: int = 0
    platform_breakdown: List[InventoryOverviewPlatformBreakdownResponse]


class InventoryOverviewAlertResponse(BaseModel):
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    platform_sku: str
    product_name: Optional[str] = None
    stock: int
    alert_type: str
