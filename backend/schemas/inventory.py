"""
库存管理 API 契约
"""

from datetime import date, datetime
from typing import List, Optional

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
    platform_code: str
    shop_id: str
    platform_sku: str
    remaining_qty: int
    oldest_age_days: int
    youngest_age_days: int
    weighted_avg_age_days: float
    remaining_value: float = 0.0


class InventoryAgingSummaryResponse(BaseModel):
    rows: List[InventoryAgingRowResponse] = Field(default_factory=list)
    buckets: List[InventoryAgingBucketResponse] = Field(default_factory=list)
    total_quantity: int = 0
    total_value: float = 0.0


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
