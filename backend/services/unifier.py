"""跨源合并（销售+运营）——依据优先键：product_id > order_id > platform_sku"""

from __future__ import annotations

from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.models.database import (
    FactSalesOrders,
    FactProductMetrics,
    DimProduct,
)


def rebuild_unified(db: Session) -> Dict[str, Any]:
    """占位实现：目前事实表已按维度键入库，此处主要返回统计。
    后续可扩展跨表物化视图或汇总表。
    """
    sales = db.query(FactSalesOrders).count()
    metrics = db.query(FactProductMetrics).count()
    products = db.query(DimProduct).count()
    return {"sales_rows": sales, "metrics_rows": metrics, "products": products}


