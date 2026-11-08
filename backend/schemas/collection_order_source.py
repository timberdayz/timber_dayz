"""采集配置「订单域来源」审计的响应契约（语义层 SSOT 改造 · 阶段 6）。

为什么单独一个模块
------------------
``backend/schemas/collection.py`` 是历史文件，仓库基线里它就没有通过
``black --check``（整份文件的历史排版债务）。本轮新增的契约放在独立模块里，
保证**新增文件本身**是干净的，不去顺手重排历史文件。

来源事实
--------
实测（2026-11）：``b_class.fact_shopee_orders_*`` / ``b_class.fact_tiktok_orders_*``
里的数据**实际由 miaoshou 采集器写入**（行的 shop_account_id 全是 ``miaoshou_real_001``），
而 shopee / tiktok 自己的采集配置里**没有** orders 域。

=> 表名里的平台前缀不等于采集器：某个平台的采集配置没有 orders 域时，
   直接提示「该平台订单需由 miaoshou 采集器提供」。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

__all__ = [
    "CollectionOrderSourceAuditResponse",
    "CollectionOrderSourceSummary",
    "CollectionOrderSourceWarning",
]


class CollectionOrderSourceWarning(BaseModel):
    """一条采集配置的订单域来源提示。"""

    platform: str
    config_id: Optional[int] = None
    config_name: str = ""
    warning: str
    reason: str
    data_domains: List[str] = Field(default_factory=list)


class CollectionOrderSourceSummary(BaseModel):
    """订单域来源提示的汇总。"""

    checked_config_count: int = 0
    warning_count: int = 0
    source_notes: Dict[str, str] = Field(default_factory=dict)


class CollectionOrderSourceAuditResponse(BaseModel):
    """采集侧订单域来源巡检的结论。"""

    summary: CollectionOrderSourceSummary
    warnings: List[CollectionOrderSourceWarning] = Field(default_factory=list)
