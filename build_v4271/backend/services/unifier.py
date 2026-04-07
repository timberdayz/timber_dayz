"""跨源合并(销售+运营)——依据优先键:product_id > order_id > platform_sku"""

from __future__ import annotations

from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.models.database import (
    # [DELETED] v4.19.0: FactSalesOrders (FactOrder 别名) 已删除,使用 b_class.fact_{platform}_orders_{granularity} 替代
    FactProductMetrics,
    DimProduct,
)


def rebuild_unified(db: Session) -> Dict[str, Any]:
    """占位实现:目前事实表已按维度键入库,此处主要返回统计。
    后续可扩展跨表物化视图或汇总表。
    """
    # [DELETED] v4.19.0: FactSalesOrders 已删除,订单数据现在在 b_class.fact_{platform}_orders_{granularity}
    # [TODO] 需要查询 b_class schema 下的分表来统计订单数据
    sales = 0  # 暂时返回0,待实现新的查询逻辑
    metrics = db.query(FactProductMetrics).count()
    products = db.query(DimProduct).count()
    return {"sales_rows": sales, "metrics_rows": metrics, "products": products}


