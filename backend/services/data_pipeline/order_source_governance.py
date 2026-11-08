"""订单域来源治理巡检（语义层 SSOT 改造 · 阶段 6 · 任务 6.1）。

背景
----
实测（2026-11）：``b_class.fact_shopee_orders_*`` / ``b_class.fact_tiktok_orders_*``
里的数据**实际由 miaoshou 采集器写入**（行的 shop_account_id 全是 ``miaoshou_real_001``），
而 shopee / tiktok 自己的采集配置里**没有** orders 域；
``fact_miaoshou_orders_*`` 与 shopee/tiktok 的 manual 表在 2026-11 都是 0 行。

=> **表名里的平台前缀不等于采集器**。排查「订单数据没有」时应该去 miaoshou 采集侧看，
   而不是去 shopee / tiktok 的采集配置里找 orders 域。

本模块做两件事（**不改数据库、不改迁移**）
------------------------------------------
1. 来源约定登记在 ``backend/services/collection_contracts.py``
   （``ORDER_SOURCE_PROVIDER_BY_PLATFORM``）—— 那是**唯一**的代码级事实源；
2. 巡检采集配置：shopee / tiktok 的采集配置**不含 orders 域**时，直接提示
   「shopee 订单需由 miaoshou 采集器提供」。

[注意] 边界：采集配置是**数据库表**（``core.collection_configs``），
   所以这里只做「校验 + 提示」，不通过迁移去改表里的数据。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.collection_contracts import (
    build_missing_order_source_note,
    build_order_source_note,
    get_order_source_provider,
)

__all__ = [
    "CollectionOrderSourceAuditItem",
    "CollectionOrderSourceAuditReport",
    "audit_collection_config_order_sources",
    "collect_collection_order_source_audit",
    "order_source_notes",
]


ORDER_DATA_DOMAIN = "orders"


@dataclass(frozen=True)
class CollectionOrderSourceAuditItem:
    """一条采集配置的来源提示。"""

    platform: str
    config_id: int | None
    config_name: str
    warning: str
    reason: str
    data_domains: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "config_id": self.config_id,
            "config_name": self.config_name,
            "warning": self.warning,
            "reason": self.reason,
            "data_domains": list(self.data_domains),
        }


@dataclass(frozen=True)
class CollectionOrderSourceAuditReport:
    """一次采集侧来源巡检的结论。"""

    items: list[CollectionOrderSourceAuditItem] = field(default_factory=list)
    checked_config_count: int = 0
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def warning_count(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_config_count": self.checked_config_count,
            "warning_count": self.warning_count,
            "warnings": [item.to_dict() for item in self.items],
            "source_notes": dict(self.notes),
        }


def order_source_notes() -> dict[str, str]:
    """各平台的来源标注（用于接口/文档回显）。"""
    notes: dict[str, str] = {}
    for platform in ("shopee", "tiktok"):
        note = build_order_source_note(platform)
        if note:
            notes[platform] = note
    return notes


def _normalize_domains(raw: Any) -> list[str]:
    """把 ``data_domains`` 归一成字符串列表。

    [注意] 用原生 SQL 读 ``core.collection_configs.data_domains``（JSON 列）时，
    asyncpg 默认把 JSON **当字符串**返回（仓库既有测试也是这么处理的：
    ``if isinstance(value, str): value = json.loads(value)``）=> 这里必须能吃
    JSON 文本，否则 ``["products"]`` 会被当成一个域名字符串。
    """
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        text_value = raw.strip()
        if text_value.startswith("[") or text_value.startswith("{"):
            try:
                raw = json.loads(text_value)
            except (TypeError, ValueError):
                raw = [text_value]
        else:
            raw = [text_value]
    if isinstance(raw, dict):
        raw = list(raw.keys())
    if not isinstance(raw, (list, tuple, set)):
        return []
    domains: list[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value and value not in domains:
            domains.append(value)
    return domains


def _config_attr(config: Any, name: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def audit_collection_config_order_sources(
    configs: Iterable[Any],
) -> CollectionOrderSourceAuditReport:
    """巡检采集配置里的订单域来源（纯函数，便于单测）。

    判定（两个方向都要说清楚）：

    1. 配置**不含** orders 域 —— 这不是「漏配」，而是**正常形态**：
       该平台的订单数据由**别的采集器**提供（miaoshou）。
       => 直接提示「shopee 订单需由 miaoshou 采集器提供」，
       免得排查的人以为「配置漏了 orders 域」。
    2. 配置**含** orders 域 —— 该平台自己也在采订单，与真实来源（miaoshou）
       **重复采集**，口径可能打架 => 单独点名。
    """
    items: list[CollectionOrderSourceAuditItem] = []
    notes = order_source_notes()
    checked = 0

    for config in configs or []:
        if not bool(_config_attr(config, "is_active", True)):
            continue
        platform = str(_config_attr(config, "platform", "") or "").strip().lower()
        provider = get_order_source_provider(platform)
        if not provider:
            continue
        domains = _normalize_domains(_config_attr(config, "data_domains", []))
        checked += 1
        if ORDER_DATA_DOMAIN not in domains:
            items.append(
                CollectionOrderSourceAuditItem(
                    platform=platform,
                    config_id=_config_attr(config, "id", None),
                    config_name=str(_config_attr(config, "name", "") or ""),
                    warning=build_missing_order_source_note(platform) or "",
                    reason="orders_domain_provided_by_other_collector",
                    data_domains=domains,
                )
            )
            continue

        items.append(
            CollectionOrderSourceAuditItem(
                platform=platform,
                config_id=_config_attr(config, "id", None),
                config_name=str(_config_attr(config, "name", "") or ""),
                warning=(
                    f"{platform} 采集配置也声明了 orders 域，"
                    f"与 {provider} 采集器重复采集"
                ),
                reason="duplicate_orders_domain",
                data_domains=domains,
            )
        )

    return CollectionOrderSourceAuditReport(
        items=items, checked_config_count=checked, notes=notes
    )


async def collect_collection_order_source_audit(
    db: AsyncSession,
    *,
    platform: str | None = None,
) -> CollectionOrderSourceAuditReport:
    """从 ``core.collection_configs`` 读取启用中的配置并巡检。"""
    params: dict[str, Any] = {}
    sql = """
        SELECT id, name, platform, data_domains, is_active
        FROM core.collection_configs
        WHERE is_active IS TRUE
    """
    if platform:
        sql += " AND platform = :platform"
        params["platform"] = str(platform).strip().lower()
    sql += " ORDER BY platform, id"

    result = await db.execute(text(sql), params)
    configs = [
        {
            "id": row[0],
            "name": row[1],
            "platform": row[2],
            "data_domains": row[3],
            "is_active": row[4],
        }
        for row in result.fetchall()
    ]
    return audit_collection_config_order_sources(configs)
