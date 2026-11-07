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
    #: [*] 批次 D: 冲突明细 —— 同一列名被对齐到**两个**语义键。
    conflicts: List[AliasRecord]
    created: int
    unchanged: int


#: [*] 批次 D: 全局别名的域占位符 —— 用户在任何一个域确认过的对齐, 其它域也生效
#: (D-3 决策「全局沉淀, 一处生效」)。
GLOBAL_ALIAS_DOMAIN = "*"

#: 冲突记录的标准字段前缀 —— 让冲突行与正常行在唯一约束上不撞
CONFLICT_FIELD_PREFIX = "__conflict__"


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
        global_scope: bool = True,
    ) -> List[AliasRecord]:
        """收集「用户确认过」的绑定, 作为可沉淀的别名。

        [*] 批次 D: ``global_scope=True``(默认)时沉淀成**全局**别名 ——
        用户在一个域对齐一次, 其它域/其它模板自动命中(D-3 决策)。
        """
        aliases: List[AliasRecord] = []
        seen = set()
        scope_domain = GLOBAL_ALIAS_DOMAIN if global_scope else data_domain
        # [*] 批次 D: 全局沉淀必须**三个维度都不限**才算「全局」。
        #     只把 data_domain 放开、platform_code / granularity 还带着的话,
        #     同一个列名在另一个平台再对齐一次会变成「另一条记录」——
        #     冲突检测就漏了, 「一处生效」也名不副实。
        scope_platform = None if global_scope else platform_code
        scope_granularity = None if global_scope else granularity
        for binding in header_bindings or []:
            if binding.get("semantic_review_status") != "confirmed_semantic":
                continue
            standard_field = binding.get("semantic_key")
            raw_alias = binding.get("source_header") or binding.get("raw_name") or binding.get("display_name")
            if not standard_field or not raw_alias:
                continue
            key = (scope_domain, standard_field, raw_alias, scope_platform, scope_granularity)
            if key in seen:
                continue
            seen.add(key)
            aliases.append(
                {
                    "data_domain": scope_domain,
                    "standard_field": standard_field,
                    "raw_alias": raw_alias,
                    "platform_code": scope_platform,
                    "granularity": scope_granularity,
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
        global_scope: bool = True,
    ) -> AliasUpsertSummary:
        """把用户确认过的对齐沉淀进全局别名表。

        [*] 批次 D 的硬原则: **冲突不静默覆盖**。

        同一个列名被对齐到**两个**语义键时:
        * 原记录**保持不动**;
        * 额外写一条 ``status='conflict'`` 的记录;
        * 返回 ``conflicts`` 明细, 由上层报警 + 交人裁决。

        以前这里是「存在就跳过」—— 冲突被**静默丢弃**, 人根本不知道
        有两个模板对同一个列名有不同理解。
        """
        aliases = self.collect_aliases_from_template_bindings(
            data_domain=data_domain,
            platform_code=platform_code,
            granularity=granularity,
            header_bindings=header_bindings,
            global_scope=global_scope,
        )
        if not aliases:
            return AliasUpsertSummary(aliases=[], conflicts=[], created=0, unchanged=0)

        now = datetime.now(timezone.utc)
        created = 0
        unchanged = 0
        conflicts: List[AliasRecord] = []
        try:
            for alias in aliases:
                conflict = await self._detect_conflict(
                    db,
                    data_domain=alias["data_domain"],
                    raw_alias=alias["raw_alias"],
                    standard_field=alias["standard_field"],
                    platform_code=alias.get("platform_code"),
                    granularity=alias.get("granularity"),
                )
                if conflict is not None:
                    conflicts.append(conflict)
                    await self._insert_conflict_row(db, conflict, now=now)
                    continue
                inserted = await self._insert_alias_row(db, alias, now=now)
                if inserted:
                    created += 1
                else:
                    unchanged += 1
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.warning("[SemanticAlias] 别名沉淀失败: %s", exc)
            return AliasUpsertSummary(
                aliases=aliases, conflicts=conflicts, created=created, unchanged=unchanged
            )

        if conflicts:
            logger.warning(
                "[SemanticAlias] 别名冲突 %s 条, 已落 conflict 等待裁决 (未覆盖原记录)",
                len(conflicts),
            )
        return AliasUpsertSummary(
            aliases=aliases, conflicts=conflicts, created=created, unchanged=unchanged
        )

    async def _detect_conflict(
        self,
        db: AsyncSession,
        *,
        data_domain: str,
        raw_alias: str,
        standard_field: str,
        platform_code: Optional[str],
        granularity: Optional[str],
    ) -> Optional[AliasRecord]:
        """同一列名已经指向**别的**语义键 ⇒ 冲突。"""
        result = await db.execute(
            text(
                """
                SELECT standard_field
                FROM semantic.semantic_field_aliases
                WHERE data_domain = :data_domain
                  AND raw_alias = :raw_alias
                  AND COALESCE(platform_code, '') = COALESCE(:platform_code, '')
                  AND COALESCE(granularity, '') = COALESCE(:granularity, '')
                  AND status = 'active'
                  AND standard_field <> :standard_field
                LIMIT 1
                """
            ),
            {
                "data_domain": data_domain,
                "raw_alias": raw_alias,
                "standard_field": standard_field,
                "platform_code": platform_code,
                "granularity": granularity,
            },
        )
        existing = result.first()
        if not existing:
            return None
        return {
            "data_domain": data_domain,
            "standard_field": standard_field,
            "raw_alias": raw_alias,
            "platform_code": platform_code,
            "granularity": granularity,
            "source": "template_confirmed",
            "conflict_with": existing[0],
        }

    async def _insert_alias_row(
        self, db: AsyncSession, alias: AliasRecord, *, now: datetime
    ) -> bool:
        """写入一条别名; 已存在同 (域, 语义键, 列名) 则幂等跳过。"""
        result = await db.execute(
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
        return bool(result.rowcount)

    async def _insert_conflict_row(
        self, db: AsyncSession, conflict: AliasRecord, *, now: datetime
    ) -> None:
        """写入一条 ``conflict`` 记录(不覆盖原记录)。"""
        conflict_field = f"{CONFLICT_FIELD_PREFIX}{conflict['standard_field']}"
        await db.execute(
            text(
                """
                INSERT INTO semantic.semantic_field_aliases (
                    data_domain, standard_field, raw_alias, platform_code, granularity,
                    source, confidence, status, created_at, updated_at
                )
                SELECT
                    :data_domain, :standard_field, :raw_alias, :platform_code, :granularity,
                    'manual', 0.500, 'conflict', :now, :now
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM semantic.semantic_field_aliases existing
                    WHERE existing.data_domain = :data_domain
                      AND existing.standard_field = :standard_field
                      AND existing.raw_alias = :raw_alias
                      AND COALESCE(existing.platform_code, '') = COALESCE(:platform_code, '')
                      AND COALESCE(existing.granularity, '') = COALESCE(:granularity, '')
                      AND existing.status = 'conflict'
                )
                """
            ),
            {**conflict, "standard_field": conflict_field, "now": now},
        )
