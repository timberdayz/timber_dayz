"""Semantic alias registry helpers for template governance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from modules.core.logger import get_logger

# 导入方向: registry -> field_registry。
#
# ``semantic_field_registry`` **不** import 本模块(它只在注释里提到过),
# 所以这个方向不会形成环; 若将来它反过来 import 了这里, 就把下面的 import
# 改成函数内延迟导入即可(语义不变)。
from backend.services.semantic_field_registry import (
    CALIBER_PAID,
    CALIBER_PLACED,
    DOMAIN_SEMANTIC_ALIASES,
    LEGACY_CALIBER_ALIAS_CONFIDENCE,
    PLATFORM_CALIBER_HISTORY,
    SEMANTIC_FIELD_ALIASES,
    SEMANTIC_FIELD_DEFINITIONS,
    apply_caliber_history,
    is_block_column_alias,
    is_legacy_caliber_alias,
    normalize_semantic_alias,
)


logger = get_logger(__name__)


AliasRecord = Dict[str, Any]


#: 别名 seed 的默认来源/置信度/状态 —— 与
#: ``sql/semantic/semantic_alias_registry.sql`` 的 INSERT 段保持一致。
ALIAS_SEED_SOURCE = "builtin"
ALIAS_SEED_CONFIDENCE = 1.000
ALIAS_SEED_STATUS = "active"


#: 别名里的**口径标记** —— 出现哪个口径词, 就说明这个别名说的是哪套口径。
#:
#: 「已确定订单」是 shopee 上「已下单」的旧叫法(实测两者差 4.25%,
#: 属同一口径的措辞迁移), 所以它算 placed 口径。
#: 「已确认订单」**刻意不在这里** —— 真实数据里它没有任何数值,
#: 无从判断它对应哪个口径 ⇒ 宁可落 unknown, 也不猜。
_CALIBER_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("已付款", CALIBER_PAID),
    ("已确定订单", CALIBER_PLACED),
    ("已下订单", CALIBER_PLACED),
    ("已下单", CALIBER_PLACED),
)


def detect_alias_caliber(raw_alias: Optional[str]) -> Optional[str]:
    """判断一个别名说的是哪套口径; 别名里没有口径词则返回 ``None``。"""
    text_value = str(raw_alias or "")
    for marker, caliber in _CALIBER_MARKERS:
        if marker in text_value:
            return caliber
    return None


def _products_relevant_standard_fields(data_domain: str) -> List[str]:
    """该数据域用到的标准字段集合。

    两个来源的并集:

    1. ``DOMAIN_SEMANTIC_ALIASES[domain]`` 里出现过的标准字段
       —— 域限定别名表已经声明「这个域要用这些字段」;
    2. ``SEMANTIC_FIELD_DEFINITIONS`` 里 ``domain`` 等于该域的字段
       —— 字段定义自己声明了归属。

    其它域的字段**不进**这里 ⇒ 全局别名不会跨域污染。
    """
    fields = set(DOMAIN_SEMANTIC_ALIASES.get(data_domain, {}).keys())
    for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
        if str(meta.get("domain") or "") == data_domain:
            fields.add(key)
    return sorted(fields)


def build_domain_alias_records(data_domain: str = "products") -> List[AliasRecord]:
    """从 ``semantic_field_registry`` 的字典派生某个数据域的别名记录。

    这份字典是**唯一事实源**: 别名不再手写, 所以 DB seed / Python 侧派生别名
    / 推断索引三边不会再分叉。

    合并规则(顺序即优先级):

    1. **域限定别名表**(:data:`DOMAIN_SEMANTIC_ALIASES`) —— 权威。
       它登记的才是**真实表头**(「商品编号」「销售额（已付款订单）」…)。
    2. **全局别名表**(:data:`SEMANTIC_FIELD_ALIASES`) —— 只取该域用到的
       标准字段, 补上「销售额」「订单数」这类**裸名**。

    两条硬规则:

    * **口径不许混**: 全局别名若带口径词、且与该标准字段声明的 ``caliber``
      相反, 直接丢弃(实测两套口径的销售额平均差 5.15%, 混了就是错数);
    * **一个列名只认一个标准字段**: 同一个别名被两个标准字段认领时,
      域限定的赢, 其余丢弃(否则 PG 侧解析结果不确定)。

    Returns:
        记录列表, 每条含 ``data_domain`` / ``standard_field`` / ``raw_alias`` /
        ``source`` / ``confidence`` / ``status`` / ``normalized_alias`` /
        ``normalized_alias_history``。
    """
    domain_aliases = DOMAIN_SEMANTIC_ALIASES.get(data_domain, {})
    relevant_fields = _products_relevant_standard_fields(data_domain)

    claimed: Dict[str, str] = {}
    ordered: List[Tuple[str, str]] = []

    def _claim(standard_field: str, raw_alias: Any) -> None:
        alias = str(raw_alias or "").strip()
        if not alias:
            return
        # 报表分块列(末尾 .N)不是基础指标本身, 不落标准字段。
        # 实测: tiktok 商品月报的基础列 == .1+.2+.3+.4(701/777 行成立),
        # ⇒ .N 是第 N 块, 把它算成"去重版"就是静默失真。
        if is_block_column_alias(alias):
            return
        owner = claimed.get(alias)
        if owner is not None:
            # 已被别的标准字段认领 ⇒ 不再重复认领(域限定优先)。
            return
        claimed[alias] = standard_field
        ordered.append((standard_field, alias))

    # 1) 域限定别名(权威口径)
    for standard_field, aliases in domain_aliases.items():
        for alias in aliases:
            _claim(standard_field, alias)

    # 2) 全局别名(补裸名), 只取该域用到的字段, 且不许与口径冲突
    for standard_field in relevant_fields:
        field_caliber = SEMANTIC_FIELD_DEFINITIONS.get(standard_field, {}).get(
            "caliber"
        )
        for alias in SEMANTIC_FIELD_ALIASES.get(standard_field, []):
            alias_caliber = detect_alias_caliber(alias)
            if field_caliber and alias_caliber and field_caliber != alias_caliber:
                continue
            _claim(standard_field, alias)

    records: List[AliasRecord] = []
    for standard_field, alias in sorted(ordered):
        normalized = normalize_semantic_alias(alias)
        records.append(
            {
                "data_domain": data_domain,
                "standard_field": standard_field,
                "raw_alias": alias,
                "source": ALIAS_SEED_SOURCE,
                "confidence": (
                    LEGACY_CALIBER_ALIAS_CONFIDENCE
                    if is_legacy_caliber_alias(alias)
                    else ALIAS_SEED_CONFIDENCE
                ),
                "status": ALIAS_SEED_STATUS,
                "normalized_alias": normalized,
                "normalized_alias_history": _apply_history_variants(normalized),
            }
        )
    return records


def _apply_history_variants(normalized: str) -> str:
    """把归一化别名按各平台的口径沿革折算, 返回等价形态(分号分隔)。

    沿革表按平台登记, 同一个词在不同平台的沿革不一定一样; 没有登记沿革的
    平台原样保留。返回空串表示「折算后没有任何变化」。
    """
    if not normalized:
        return ""
    variants: List[str] = []
    for platform_code in sorted(PLATFORM_CALIBER_HISTORY):
        folded = apply_caliber_history(normalized, platform_code)
        if folded and folded != normalized and folded not in variants:
            variants.append(folded)
    return ";".join(variants)


#: 内置别名 —— **由字典派生**, 不再手写。
#:
#: 保持 ``list[dict]`` 形状与键名不变, ``SemanticAliasRegistryService`` 的
#: 既有行为(按列名原文取值)也不变。
BUILTIN_ALIASES: List[AliasRecord] = [
    {
        "data_domain": record["data_domain"],
        "standard_field": record["standard_field"],
        "raw_alias": record["raw_alias"],
    }
    for record in build_domain_alias_records("products")
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
            if (
                alias.get("data_domain") != data_domain
                or alias.get("standard_field") != standard_field
            ):
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
            raw_alias = (
                binding.get("source_header")
                or binding.get("raw_name")
                or binding.get("display_name")
            )
            if not standard_field or not raw_alias:
                continue
            key = (
                scope_domain,
                standard_field,
                raw_alias,
                scope_platform,
                scope_granularity,
            )
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
                aliases=aliases,
                conflicts=conflicts,
                created=created,
                unchanged=unchanged,
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
