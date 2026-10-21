"""
库存管理 API 契约
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class InventoryAdjustmentLineCreate(BaseModel):
    platform_code: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=64)
    platform_sku: str = Field(..., min_length=1, max_length=128)
    qty_delta: int = Field(..., description="正数表示增加，负数表示减少")
    unit_cost: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class InventoryAdjustmentCreateRequest(BaseModel):
    adjustment_date: date = Field(..., description="调整日期")
    reason: str = Field(..., min_length=1, max_length=64, description="调整原因")
    notes: Optional[str] = Field(None, description="调整单备注")
    lines: List[InventoryAdjustmentLineCreate] = Field(
        ..., min_length=1, description="至少包含一条调整行"
    )


class InventoryAdjustmentLineResponse(BaseModel):
    adjustment_line_id: int
    platform_code: str
    shop_id: str
    platform_sku: str
    qty_delta: int
    unit_cost: Optional[float] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class InventoryAdjustmentResponse(BaseModel):
    adjustment_id: str
    adjustment_date: date
    status: str
    reason: str
    notes: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    lines: List[InventoryAdjustmentLineResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class InventoryGrnLineResponse(BaseModel):
    grn_line_id: int
    po_line_id: int
    platform_sku: str
    qty_received: int
    unit_cost: float
    currency: str
    ext_value: float
    base_ext_value: float

    class Config:
        from_attributes = True


class InventoryGrnResponse(BaseModel):
    grn_id: str
    po_id: str
    receipt_date: date
    warehouse: Optional[str] = None
    status: str
    created_by: str
    created_at: datetime
    lines: List[InventoryGrnLineResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class InventoryGrnPostResponse(BaseModel):
    grn_id: str
    status: str
    posted_entries: int


class InventoryOpeningBalanceCreateRequest(BaseModel):
    period: str = Field(..., min_length=1, max_length=16)
    platform_code: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=64)
    platform_sku: str = Field(..., min_length=1, max_length=128)
    received_date: Optional[date] = Field(None, description="期初入库日期")
    opening_age_days: Optional[int] = Field(None, ge=0, description="期初库龄天数")
    opening_qty: int = Field(..., description="期初数量")
    opening_cost: float = Field(0.0, ge=0, description="期初单位成本")
    opening_value: Optional[float] = Field(None, ge=0, description="期初总价值")
    source: str = Field("manual", min_length=1, max_length=64)
    migration_batch_id: Optional[str] = Field(None, max_length=64)


class InventoryOpeningBalanceResponse(BaseModel):
    balance_id: int
    period: str
    platform_code: str
    shop_id: str
    platform_sku: str
    received_date: Optional[date] = None
    opening_age_days: Optional[int] = None
    opening_qty: int
    opening_cost: float
    opening_value: float
    source: str
    migration_batch_id: Optional[str] = None
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryAgingBucketResponse(BaseModel):
    bucket: str
    quantity: int = 0
    inventory_value: float = 0.0
    sku_count: int = 0


class InventoryAgingRowResponse(BaseModel):
    snapshot_date: date
    platform_code: str
    sku_key: str
    platform_sku: Optional[str] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    current_qty: int
    previous_qty: Optional[int] = None
    qty_delta: Optional[int] = None
    age_anchor_date: Optional[date] = None
    age_days: int
    reset_reason: str
    inventory_value: float = 0.0
    bucket: str


class InventoryAgingHistoryPointResponse(BaseModel):
    snapshot_date: date
    platform_code: str
    sku_key: str
    platform_sku: Optional[str] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    current_qty: int
    previous_qty: Optional[int] = None
    qty_delta: Optional[int] = None
    age_anchor_date: Optional[date] = None
    age_days: Optional[int] = None
    reset_reason: str
    inventory_value: float = 0.0
    bucket: Optional[str] = None


class InventoryAgingSummaryResponse(BaseModel):
    rows: List[InventoryAgingRowResponse] = Field(default_factory=list)
    buckets: List[InventoryAgingBucketResponse] = Field(default_factory=list)
    total_sku_count: int = 0
    total_quantity: int = 0
    total_value: float = 0.0


class SkuClearanceRankingItemResponse(BaseModel):
    """SKU 级滞销清单的一行。

    库龄/库存/动销列来自只读视图 `api.sku_clearance_ranking_module`；
    定价列（档位、折扣率、最低售价、清货回款）由 service 调
    `backend/services/product_pricing_service.py` 的纯函数补齐——
    **SQL 里不重写定价公式**，口径只有一处。
    """

    snapshot_date: Optional[date] = None
    platform_code: str
    product_sku: str
    sku_key: Optional[str] = None
    product_name: Optional[str] = None
    current_qty: int = 0
    on_hand_qty: int = 0
    inventory_value: float = 0.0
    warehouse_count: int = 0
    age_anchor_date: Optional[date] = None
    age_days: int = 0
    age_bucket: Optional[str] = None
    reset_reason: Optional[str] = None
    estimated_turnover_days: Optional[float] = None
    daily_avg_sales: Optional[float] = None
    is_stagnant: Optional[bool] = None
    estimated_stagnant_days: Optional[int] = None
    stagnant_snapshot_count: Optional[int] = None
    risk_level: str = "low"
    clearance_priority_score: float = 0.0
    sku_id: Optional[int] = None
    default_purchase_cost: Optional[float] = None
    reference_selling_price: Optional[float] = None
    min_selling_price_override: Optional[float] = None
    # —— 定价字段（service 用纯函数补齐）——
    pricing_tier_label: Optional[str] = None
    current_discount_rate: Optional[float] = None
    current_target_margin_rate: Optional[float] = None
    clearance_max_discount_rate: Optional[float] = None
    min_selling_price: Optional[float] = None
    min_selling_price_source: Optional[str] = None
    clearance_recovery_amount: Optional[float] = None
    # 未匹配 ERP 主数据的 SKU 照常返回，但定价字段为空，前端据此标「未匹配主数据」
    pricing_matched_erp: bool = False


class SkuClearanceRankingSummaryResponse(BaseModel):
    sku_count: int = 0
    total_quantity: int = 0
    total_inventory_value: float = 0.0
    by_risk_level: Dict[str, int] = Field(default_factory=dict)
    by_age_bucket: Dict[str, int] = Field(default_factory=dict)
    # 缺参考售价的 SKU 数：主数据缺口直接暴露在业务界面上，
    # 运营一眼知道哪些滞销品算不出清货回款
    missing_reference_price_count: int = 0


class SkuClearanceRankingResponse(BaseModel):
    summary: SkuClearanceRankingSummaryResponse = Field(
        default_factory=SkuClearanceRankingSummaryResponse
    )
    items: List[SkuClearanceRankingItemResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class InventoryBalanceSummaryResponse(BaseModel):
    platform_code: str
    shop_id: str
    platform_sku: str
    opening_qty: int = 0
    qty_in: int = 0
    qty_out: int = 0
    current_qty: int = 0


class InventoryBalanceDetailResponse(InventoryBalanceSummaryResponse):
    opening_cost: float = 0.0
    average_cost: float = 0.0
    current_value: float = 0.0


class InventoryLedgerRowResponse(BaseModel):
    ledger_id: int
    platform_code: str
    shop_id: str
    platform_sku: str
    transaction_date: date
    movement_type: str
    qty_in: int
    qty_out: int
    qty_before: int
    qty_after: int
    avg_cost_before: float
    avg_cost_after: float
    link_grn_id: Optional[str] = None
    link_order_id: Optional[str] = None
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryAlertResponse(BaseModel):
    platform_code: str
    shop_id: str
    platform_sku: str
    current_qty: int
    safety_stock: int
    alert_type: str
    delta_qty: Optional[int] = None


class InventoryReconciliationResponse(BaseModel):
    platform_code: str
    shop_id: str
    platform_sku: str
    internal_qty: int
    external_qty: int
    delta_qty: int
    status: str
