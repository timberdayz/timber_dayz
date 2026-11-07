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


class InventoryOverviewRestockTierResponse(BaseModel):
    """业务定价档位（0 / 60 / 90 / 120）的一档。

    与看板汇总卡、行级 ``restock_tier``、商品中心定价档**同一套口径**。
    """

    tier: str
    label: str
    threshold_days: int
    value: float = 0.0
    row_count: int = 0
    sku_count: int = 0


class InventoryOverviewSummaryResponse(BaseModel):
    total_products: int
    total_stock: int
    total_value: float
    low_stock_count: int
    out_of_stock_count: int
    # 距上次进货天数分档的**去重 SKU 数**（不是 SKU×仓 的行数）
    # ⚠ 旧标准指标（≥180 天 / 90~180 天 / <30 天），口径**不变**，
    #   与下面的业务定价档位是**两回事**，两者并存。
    deep_stagnant_sku_count: int = 0
    mid_stagnant_sku_count: int = 0
    active_sku_count: int = 0
    # 业务定价档位分组（互斥 4 档，SKU 数与货值都能加起来）
    restock_tiers: List[InventoryOverviewRestockTierResponse] = []
    platform_breakdown: List[InventoryOverviewPlatformBreakdownResponse]


class InventoryOverviewAlertResponse(BaseModel):
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    platform_sku: str
    product_name: Optional[str] = None
    stock: int
    alert_type: str
