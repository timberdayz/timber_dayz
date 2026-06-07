"""Semantic alias registry helpers for template governance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from modules.core.logger import get_logger


logger = get_logger(__name__)


AliasRecord = Dict[str, Any]


BUILTIN_ALIASES: List[AliasRecord] = [
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "商品ID"},
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "产品ID"},
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "商品 ID"},
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "product_id"},
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "Product ID"},
    {"data_domain": "products", "standard_field": "product_id", "raw_alias": "item_id"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "商品名称"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "产品名称"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "商品标题"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "商品名"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "product_name"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "Product Name"},
    {"data_domain": "products", "standard_field": "product_name", "raw_alias": "title"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "商品状态"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "状态"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "发品状态"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "item_status"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "Item Status"},
    {"data_domain": "products", "standard_field": "item_status", "raw_alias": "status"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "已付款订单"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "已确认订单"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "已确定订单"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "订单数"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "订单数量"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "order_count"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "Order Count"},
    {"data_domain": "products", "standard_field": "order_count", "raw_alias": "orders"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "销售额"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "销售金额"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "GMV"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "sales_amount"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "Sales Amount"},
    {"data_domain": "products", "standard_field": "sales_amount", "raw_alias": "revenue"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "件数"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "销量"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "销售数量"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "商品成交件数"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "sales_volume"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "Sales Volume"},
    {"data_domain": "products", "standard_field": "sales_volume", "raw_alias": "qty"},
    {"data_domain": "products", "standard_field": "impressions", "raw_alias": "曝光次数"},
    {"data_domain": "products", "standard_field": "impressions", "raw_alias": "impressions"},
    {"data_domain": "products", "standard_field": "impressions", "raw_alias": "Impressions"},
    {"data_domain": "products", "standard_field": "clicks", "raw_alias": "点击次数"},
    {"data_domain": "products", "standard_field": "clicks", "raw_alias": "clicks"},
    {"data_domain": "products", "standard_field": "clicks", "raw_alias": "Clicks"},
    {"data_domain": "products", "standard_field": "conversion_rate", "raw_alias": "转化率"},
    {"data_domain": "products", "standard_field": "conversion_rate", "raw_alias": "conversion_rate"},
    {"data_domain": "products", "standard_field": "conversion_rate", "raw_alias": "Conversion Rate"},
    {"data_domain": "products", "standard_field": "conversion_rate", "raw_alias": "CVR"},
]


@dataclass(frozen=True)
class AliasUpsertSummary:
    aliases: List[AliasRecord]


class SemanticAliasRegistryService:
    def __init__(self, builtin_aliases: Optional[Iterable[AliasRecord]] = None) -> None:
        self._builtin_aliases = list(builtin_aliases or BUILTIN_ALIASES)

    def resolve_alias_from_row(
        self,
        raw_data: Dict[str, Any],
        *,
        data_domain: str,
        standard_field: str,
        platform_code: Optional[str] = None,
        granularity: Optional[str] = None,
        extra_aliases: Optional[Iterable[AliasRecord]] = None,
    ) -> Optional[str]:
        del platform_code, granularity
        for alias in [*self._builtin_aliases, *(extra_aliases or [])]:
            if alias.get("data_domain") != data_domain or alias.get("standard_field") != standard_field:
                continue
            value = raw_data.get(alias.get("raw_alias"))
            if value is not None and str(value).strip() != "":
                return str(value)
        return None

    def collect_aliases_from_template_bindings(
        self,
        *,
        data_domain: str,
        platform_code: Optional[str],
        granularity: Optional[str],
        header_bindings: Iterable[Dict[str, Any]],
    ) -> List[AliasRecord]:
        aliases: List[AliasRecord] = []
        seen = set()
        for binding in header_bindings or []:
            if binding.get("semantic_review_status") != "confirmed_semantic":
                continue
            standard_field = binding.get("semantic_key")
            raw_alias = binding.get("source_header") or binding.get("display_name")
            if not standard_field or not raw_alias:
                continue
            key = (data_domain, standard_field, raw_alias, platform_code, granularity)
            if key in seen:
                continue
            seen.add(key)
            aliases.append(
                {
                    "data_domain": data_domain,
                    "standard_field": standard_field,
                    "raw_alias": raw_alias,
                    "platform_code": platform_code,
                    "granularity": granularity,
                    "source": "template_confirmed",
                }
            )
        return aliases

    async def upsert_template_confirmed_aliases(
        self,
        db: AsyncSession,
        *,
        data_domain: str,
        platform_code: Optional[str],
        granularity: Optional[str],
        header_bindings: Iterable[Dict[str, Any]],
    ) -> AliasUpsertSummary:
        aliases = self.collect_aliases_from_template_bindings(
            data_domain=data_domain,
            platform_code=platform_code,
            granularity=granularity,
            header_bindings=header_bindings,
        )
        if not aliases:
            return AliasUpsertSummary(aliases=[])

        now = datetime.now(timezone.utc)
        try:
            for alias in aliases:
                await db.execute(
                    text(
                        """
                        INSERT INTO semantic.semantic_field_aliases (
                            data_domain, standard_field, raw_alias, platform_code, granularity,
                            source, confidence, status, created_at, updated_at
                        )
                        SELECT
                            :data_domain, :standard_field, :raw_alias, :platform_code, :granularity,
                            :source, 0.95, 'active', :now, :now
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM semantic.semantic_field_aliases existing
                            WHERE existing.data_domain = :data_domain
                              AND existing.standard_field = :standard_field
                              AND existing.raw_alias = :raw_alias
                              AND COALESCE(existing.platform_code, '') = COALESCE(:platform_code, '')
                              AND COALESCE(existing.granularity, '') = COALESCE(:granularity, '')
                              AND existing.status = 'active'
                        )
                        """
                    ),
                    {**alias, "now": now},
                )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.warning("[SemanticAliasRegistry] alias registry upsert skipped: %s", exc)
        return AliasUpsertSummary(aliases=aliases)
