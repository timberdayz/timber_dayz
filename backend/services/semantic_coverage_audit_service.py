"""语义层标准字段覆盖率巡检(只读)。

为什么需要它
------------
``semantic.fact_products_atomic`` 对数值型标准字段做了 ``COALESCE(x, 0)``:
**解析失败被伪装成 0**, 缺失被静默吞掉 ⇒ 没人看得见"语义映射缺失"这件事。

本服务按「平台 × 粒度」统计每个标准字段的**解析率**(该字段能被语义层解析出来的行占比),
把解析失败变成可见、可告警的信号。

两件不同的事必须分开
--------------------
* **空壳行**: ``raw_data`` 是空对象 ⇒ 入库时根本没拿到数据(采集/入库问题)。
* **解析失败**: ``raw_data`` 有内容, 但语义映射命中不了 ⇒ 映射缺失(语义问题)。

这两者的处置方式完全不同(前者要重跑采集, 后者要补别名映射)⇒
空壳行**单独计数**、**不计入解析率分母**、也**不触发解析缺失告警**。

解析率怎么算
------------
两个域都走 ``semantic.resolve_alias()`` —— 与视图里
``semantic.fact_products_atomic`` / ``semantic.fact_orders_atomic``
的取值路径**同一个函数**, 所以查出来的就是视图真正的解析口径。
视图侧的 ``COALESCE(..., 0)`` 不会把失败伪装成成功。

⚠ 为什么订单域不再按"视图列的 NULL 性"判定
------------------------------------------
旧实现按视图列的 NULL 性判定, 于是有两个坏处:

1. 视图里被 ``COALESCE(..., 0)`` 掩盖的数值列(``profit`` / ``paid_amount`` /
   ``product_quantity`` / ``buyer_count``)**无法区分"解析失败"与"真的是 0"**
   ⇒ 要么给出假的"健康"结论, 要么只能把它们排除在巡检之外;
2. 字典里登记、但视图还没输出的订单字段(``refund_amount`` / ``settled_amount`` /
   ``estimated_settlement_amount`` / ``seller_voucher``)**根本没法巡检**。

现在两个域统一走别名解析:
* 解析率 = 该字段能从 ``raw_data`` 解析出非空值的行占比;
* 口径**与视图一致**(视图也用 ``semantic.resolve_alias()``);
* 视图还没输出的那几个字段, 按 ``raw_data`` 直读口径统计 ——
  用来暴露"字典登记了别名, 但源表压根没有这一列"这种缺口(如实反映, 不假装健康)。

被巡检的字段清单
----------------
* 订单域: **从字典派生** —— ``ORDER_STANDARD_FIELDS``
  (见 ``backend/services/semantic_field_registry.py``),
  不再在本文件里维护第 4 份手写清单 ⇒ 字典增删字段, 巡检自动跟随。
* 商品域: 见 :data:`PRODUCTS_STANDARD_FIELDS` 的来源注释。

解析率 0% 时给出真实列名候选
----------------------------
光说"解析率 0%"没有行动价值 —— 运维真正要回答的是"**源表里到底叫啥**"。
所以解析率 0% 时, 巡检会从 ``raw_data`` 的**真实列名**里挑出与该标准字段
最接近的 N 个, 一并写进告警:

    tiktok/monthly 的 platform_service_fee 解析率 0%，疑似语义映射缺失（疑似列名未登记）；
    源表实际列名候选：SFP服务费 / SFP服务费(RMB) / TikTok Shop Mall服务费 / TikTok Shop Mall服务费(RMB) / FBT仓储服务费

候选**保留原始列名**(``(RMB)`` 后缀、全角括号等都不动), 归一化只用于"谁更接近"的比较;
且**只挑字典里尚未登记的列名** —— 登记过的要么已映射给别的字段, 要么是"登记了但取不到数",
都不是"列名未登记"。

平台维度诊断
------------
除了逐字段告警, 报告里还给出**平台级汇总**(``SemanticCoverageReport.platforms``):
某平台有多少个标准字段在**所有粒度下都**解析不出来 —— 这种字段通常意味着
"这个平台压根没有这一列 / 列名没登记", 比逐粒度告警更值得优先处理。

只读保证
--------
本服务只发 SELECT, 不写库、不提交事务; 查询失败时吞掉异常并返回**空报告 + 一条 warning**,
绝不把调用方(定时任务/接口)带崩。
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.semantic_field_registry import (
    DOMAIN_PLATFORM_SEMANTIC_ALIASES,
    DOMAIN_SEMANTIC_ALIASES,
    ORDER_STANDARD_FIELDS as REGISTRY_ORDER_STANDARD_FIELDS,
    SEMANTIC_FIELD_DEFINITIONS,
    normalize_semantic_alias,
    platform_applicable_fields,
)
from modules.core.logger import get_logger


logger = get_logger(__name__)


#: 解析率低于该阈值即产生 warning(可参数化)。
DEFAULT_RESOLUTION_THRESHOLD = 0.5

#: 解析率模式: 走 ``semantic.resolve_alias()``(与视图同一取值路径)。
RESOLUTION_MODE_ALIAS = "alias"

#: 解析率模式: 直接按视图列的 NULL 性判定(视图保留 NULL 的列)。
RESOLUTION_MODE_COLUMN = "column"

#: 字段类型: 文本列(NULL 或空串都算没解析出来)。
FIELD_KIND_TEXT = "text"

#: 字段类型: 数值列(NULL 才是没解析出来, 0 是合法值)。
FIELD_KIND_NUMERIC = "numeric"

#: 解析率 0% 时, 最多给出多少个真实列名候选。
DEFAULT_CANDIDATE_LIMIT = 5

#: 中文之间的相似度门槛 —— 低于它就不算「像」。
#: (中文指标名一般 4~6 字, 真正相关至少共享 2 个字 ⇒ 门槛取 0.34。)
MIN_CJK_SIMILARITY = 0.34

#: 英文/数字之间的相似度门槛 —— 英文名更长更结构化, 门槛也要更高,
#: 否则 ``platform_code`` 会因为共享 ``platform`` 前缀混进候选。
MIN_ASCII_SIMILARITY = 0.6


@dataclass(frozen=True)
class SemanticCoverageField:
    """一个被巡检的标准字段。

    - ``standard_field``: 标准字段名(报告与告警里用的名字)。
    - ``source``: alias 模式下=传给 ``semantic.resolve_alias`` 的标准字段名;
      column 模式下=视图里的列名。
    - ``kind``: 文本列/数值列, 决定 NULL 的判定口径。
    """

    standard_field: str
    source: str
    kind: str = FIELD_KIND_TEXT


@dataclass(frozen=True)
class SemanticCoverageDomain:
    """一个被巡检的语义域(商品域 / 订单域)。"""

    name: str
    relation: str
    resolution_mode: str
    fields: Tuple[SemanticCoverageField, ...]


@dataclass(frozen=True)
class SemanticCoverageEntry:
    """(平台 × 粒度 × 标准字段) 的解析率。

    ``total_rows`` 是**参与解析判定的行数**(已剔除空壳行)——
    空壳行是"没拿到数据", 不该算到映射质量头上。
    """

    platform_code: str
    granularity: str
    standard_field: str
    resolved_rows: int
    total_rows: int
    resolution_rate: float


@dataclass(frozen=True)
class SemanticCoverageGroup:
    """(平台 × 粒度) 的整体情况。"""

    platform_code: str
    granularity: str
    total_rows: int
    empty_shell_rows: int
    payload_rows: int
    unresolved_rows: int
    unresolved_rate: float


@dataclass(frozen=True)
class SemanticCoveragePlatformSummary:
    """平台维度的整体诊断(阶段 5.3)。

    * ``total_fields``: 该平台出现过的标准字段数(跨粒度去重)。
    * ``zero_fields``: 该平台下**所有粒度都**解析率为 0 的标准字段数 ——
      这种字段通常意味着「源表压根没有这一列 / 列名没登记」。
    * ``zero_standard_fields``: 上面这些字段的名字(方便调用方直接展示)。
    """

    platform_code: str
    total_fields: int
    zero_fields: int
    zero_rate: float
    zero_standard_fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticCoverageReport:
    """一次覆盖率巡检的结论。

    ``column_candidates`` 与 ``platforms`` 是阶段 5 新增的**可选**信息,
    都有默认值 ⇒ 既有调用方(按位置/关键字构造或读取)不受影响。
    """

    entries: Tuple[SemanticCoverageEntry, ...]
    empty_shell_rows: int
    unresolved_rows: int
    warnings: Tuple[str, ...]
    groups: Tuple[SemanticCoverageGroup, ...] = ()
    domain: str = ""
    threshold: float = DEFAULT_RESOLUTION_THRESHOLD
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    #: 解析率 0% 的字段 → 源表真实列名候选。
    #: key = ``"{platform_code}/{granularity}/{standard_field}"``,
    #: value = 原始列名元组(按相似度降序)。
    column_candidates: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    #: 平台维度的整体诊断。
    platforms: Tuple[SemanticCoveragePlatformSummary, ...] = ()


# ── 被巡检的字段清单 ───────────────────────────────────────────────
#
# 商品域: **从字典派生** —— ``DOMAIN_SEMANTIC_ALIASES["products"]``
# (即 ``PRODUCTS_SEMANTIC_ALIASES``) 减去 :data:`PRODUCTS_EXCLUDED_FIELDS`。
#
# 订单域: **从字典派生** —— ``ORDER_STANDARD_FIELDS``
# (见 ``backend/services/semantic_field_registry.py``), 该字典项已剔除
# ``ORDER_RETIRED_FIELDS``。
#
# ⇒ 两个域都不再在本文件里维护第 4 份手写清单: 字典增删字段, 巡检自动跟随,
#   不会再出现「字典有、巡检没有」的漏检。
#
#: 商品域**不纳入**巡检的标准字段(字典派生时的排除项)。
#:
#: 排除原因分两类:
#:
#: * **商品视图里没有这一列** —— 要么是视图内由别的列算出来的派生列
#:   (``aov`` = 销售额/订单量、``buyer_count``、``order_conversion_rate``、
#:   ``unique_*``、``page_views``、``bounce_rate``、``add_to_cart_*``、
#:   ``click_to_order_rate`` …), 要么是字典登记了但视图压根没输出
#:   (``sku_id``): 拿 ``raw_data`` 去解析它们永远是 0%
#:   ⇒ 只会刷屏假告警, 反而掩盖真问题;
#: * **下单口径(placed)字段** —— 与已付款口径是**不同的业务事实**
#:   (见 registry 的 ``PLATFORM_CALIBER_HISTORY`` 说明), 当前巡检只覆盖
#:   已付款口径主干。
#:
#: ⚠ 排除项**必须**跟着字典一起复核: 若某个字段改成了「直接从源列取值」,
#:   它就**应该**回到巡检范围内。
PRODUCTS_EXCLUDED_FIELDS: frozenset = frozenset(
    {
        # ── 商品视图里没有这一列 ──
        "aov",
        "aov_placed",
        "add_to_cart_count",
        "add_to_cart_rate",
        "add_to_cart_user_count",
        "bounce_rate",
        "buyer_count",
        "buyer_count_placed",
        "click_to_order_rate",
        "order_conversion_rate",
        "order_conversion_rate_placed",
        "page_views",
        "product_visitor_count",
        "unique_click_to_order_rate",
        "unique_clicks",
        "unique_impressions",
        # ── 下单口径(placed)字段 ──
        "conversion_rate_placed",
        "order_count_placed",
        "sales_amount_placed",
        "sales_volume_placed",
        # ── 固定列名链(不走别名解析) ──
        "sku_id",
    }
)


def _field_kind(standard_field: str) -> str:
    """按字典里的 ``kind`` 判定字段是文本列还是数值列。

    * ``metric`` ⇒ 数值列(NULL 才算没解析出来, 0 是合法值);
    * 其余(``identity`` / ``dimension`` / ``attribute`` / ``time``)⇒ 文本列
      (NULL 或空串都算没解析出来)。
    """
    meta = SEMANTIC_FIELD_DEFINITIONS.get(standard_field) or {}
    kind = str(meta.get("kind") or "")
    return FIELD_KIND_NUMERIC if kind == "metric" else FIELD_KIND_TEXT


def _derive_products_fields() -> Tuple[SemanticCoverageField, ...]:
    """商品域巡检字段(从字典派生)。"""
    keys = set(DOMAIN_SEMANTIC_ALIASES.get("products", {}).keys())
    keys -= PRODUCTS_EXCLUDED_FIELDS
    return tuple(
        SemanticCoverageField(key, key, _field_kind(key)) for key in sorted(keys)
    )


def _derive_orders_fields() -> Tuple[SemanticCoverageField, ...]:
    """订单域巡检字段(从字典派生)。"""
    return tuple(
        SemanticCoverageField(key, key, _field_kind(key))
        for key in REGISTRY_ORDER_STANDARD_FIELDS
    )


#: 商品域巡检字段(字典派生)。
PRODUCTS_STANDARD_FIELDS: Tuple[SemanticCoverageField, ...] = _derive_products_fields()

#: 订单域巡检字段(字典派生)。
ORDERS_STANDARD_FIELDS: Tuple[SemanticCoverageField, ...] = _derive_orders_fields()


SEMANTIC_COVERAGE_DOMAINS: Dict[str, SemanticCoverageDomain] = {
    "products": SemanticCoverageDomain(
        name="products",
        relation="semantic.fact_products_atomic",
        resolution_mode=RESOLUTION_MODE_ALIAS,
        fields=PRODUCTS_STANDARD_FIELDS,
    ),
    "orders": SemanticCoverageDomain(
        name="orders",
        relation="semantic.fact_orders_atomic",
        # 订单域也走别名解析: 视图里被 COALESCE(...,0) 掩盖的数值列
        # (paid_amount / profit / product_quantity / buyer_count)只有走
        # resolve_alias 才分得清「解析失败」与「真的是 0」;
        # 字典登记了、视图还没输出的字段(settled_amount 等)也能被巡检到。
        resolution_mode=RESOLUTION_MODE_ALIAS,
        fields=ORDERS_STANDARD_FIELDS,
    ),
}


# ── 源表真实列名候选 ────────────────────────────────────────────────
#
# 为什么要它
# --------
# 光说「解析率 0%」没有行动价值 —— 运维真正要回答的是「**源表里到底叫啥**」。
# 所以解析率 0% 时, 巡检会把 ``raw_data`` 里的**真实列名**挑出来一并给出。
#
# 口径
# ----
# * 候选来自 ``raw_data`` 的 key(即源表真实表头)⇒ **原样保留**
#   (``(RMB)`` 后缀、全角括号都不动);
# * 比较前先用字典的 :func:`normalize_semantic_alias` 归一化
#   (全角括号 / 币种后缀 / 空白差异不该影响「像不像」);
# * 相似度用 :class:`difflib.SequenceMatcher` —— **确定性**, 无随机性;
# * 排序键 = ``(-相似度, 原始列名)`` ⇒ 同分时顺序也是确定的;
# * **已登记**的列名不算候选 —— 那是「登记了但取不到数」, 不是「列名未登记」。


def _reference_names(
    standard_field: str,
    *,
    domain_name: str,
    platform_code: str,
) -> Tuple[str, ...]:
    """该标准字段的**参考名**(用来跟源表真实列名比相似度)。

    全部来自字典:
    * 语义键本身(``platform_commission``);
    * 字典定义里的中文标签与别名;
    * 域级别名表(``DOMAIN_SEMANTIC_ALIASES``);
    * 平台级别名表(``DOMAIN_PLATFORM_SEMANTIC_ALIASES``)。
    """
    names: List[str] = [standard_field]
    meta = SEMANTIC_FIELD_DEFINITIONS.get(standard_field) or {}
    label = meta.get("label")
    if label:
        names.append(str(label))
    names.extend(str(alias) for alias in (meta.get("aliases") or ()))
    names.extend(
        str(alias)
        for alias in DOMAIN_SEMANTIC_ALIASES.get(domain_name, {}).get(
            standard_field, ()
        )
    )
    for per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(domain_name, {}).values():
        names.extend(str(alias) for alias in per_platform.get(standard_field, ()))
    # 去重且保持顺序(顺序只影响并列时的展示, 不影响结果集合)。
    seen: set[str] = set()
    unique: List[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return tuple(unique)


def _cjk_only(text: str) -> str:
    """只保留中日韩汉字(用来比较「中文指标名」之间的相似度)。"""
    return "".join(char for char in text if "\u4e00" <= char <= "\u9fff")


def _similarity(left: str, right: str) -> float:
    """两个归一化名字的相似度(0~1, 确定性); 低于门槛时返回 0。

    口径:
    * 两边都有中文 ⇒ **只比中文部分**(「联盟佣金」对「平台佣金」该像,
      而不是被 ``shopee`` 之类的英文前缀稀释), 门槛
      :data:`MIN_CJK_SIMILARITY`;
    * 一边中文、一边纯英文/数字 ⇒ **判 0** —— 「平台扣费」和 ``platform_code``
      不是同一个指标的两种写法, 不该因为共享 ``platform`` 前缀就算「像」;
    * 两边都没有中文 ⇒ 按整串比(``shop_account_id`` 对 ``shop_id``), 门槛
      :data:`MIN_ASCII_SIMILARITY` —— 英文名更长更结构化, 门槛也要更高,
      否则 ``platform_code`` 会因为共享 ``platform`` 前缀混进候选。
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_cjk = _cjk_only(left)
    right_cjk = _cjk_only(right)
    if left_cjk and right_cjk:
        score = difflib.SequenceMatcher(
            None, left_cjk, right_cjk, autojunk=False
        ).ratio()
        return score if score >= MIN_CJK_SIMILARITY else 0.0
    if left_cjk or right_cjk:
        return 0.0
    # autojunk=False: 关掉「popular element」启发式, 保证结果只由输入决定。
    score = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
    return score if score >= MIN_ASCII_SIMILARITY else 0.0


#: 各域「已登记列名」缓存(归一化后)—— 字典是静态的, 算一次就够。
_REGISTERED_COLUMN_NAMES_CACHE: Dict[str, frozenset] = {}


def _registered_column_names(domain_name: str) -> frozenset:
    """该域**已登记**的源表列名(归一化后)。

    已登记 = 字典的域级别名表(:data:`DOMAIN_SEMANTIC_ALIASES`)与
    平台级别名表(:data:`DOMAIN_PLATFORM_SEMANTIC_ALIASES`)里出现过的列名。

    ⇒ **已经在字典里的列名不是「列名未登记」的候选** ——
    它们要么已经映射给某个字段(问题在取值, 不在列名),
    要么是另一个字段的列(不该抢)。
    """
    cached = _REGISTERED_COLUMN_NAMES_CACHE.get(domain_name)
    if cached is not None:
        return cached
    names: set[str] = set()
    for aliases in DOMAIN_SEMANTIC_ALIASES.get(domain_name, {}).values():
        names.update(normalize_semantic_alias(alias) for alias in aliases)
    for per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(domain_name, {}).values():
        for aliases in per_platform.values():
            names.update(normalize_semantic_alias(alias) for alias in aliases)
    names.discard("")
    frozen = frozenset(names)
    _REGISTERED_COLUMN_NAMES_CACHE[domain_name] = frozen
    return frozen


def _rank_column_candidates(
    standard_field: str,
    column_names: Iterable[str],
    *,
    domain_name: str,
    platform_code: str,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> Tuple[str, ...]:
    """从源表真实列名里挑出与该标准字段**最接近**的 N 个候选。

    候选 = 源表真实列名里**字典尚未登记**的那些(登记过的要么已映射,
    要么属于别的字段)⇒ 候选本身就在回答「该登记的是不是它」。

    Args:
        standard_field: 标准字段名。
        column_names: 源表真实列名(原样)。
        domain_name: 语义域名(决定用哪张域级别名表)。
        platform_code: 平台码(仅用于日志/未来扩展)。
        limit: 最多返回几个候选。

    Returns:
        原始列名元组(按相似度降序, 同分按列名字典序)。
    """
    references = _reference_names(
        standard_field,
        domain_name=domain_name,
        platform_code=platform_code,
    )
    normalized_refs = {normalize_semantic_alias(name) for name in references}
    normalized_refs.discard("")
    if not normalized_refs:
        return ()

    registered = _registered_column_names(domain_name)
    scored: List[Tuple[float, str]] = []
    for raw_name in column_names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        normalized = normalize_semantic_alias(name)
        if not normalized:
            continue
        # 已登记的列名不是「列名未登记」的候选。
        if normalized in registered:
            continue
        score = max(_similarity(normalized, ref) for ref in normalized_refs)
        if score <= 0:
            continue
        scored.append((-score, name))
    scored.sort()
    return tuple(name for _, name in scored[: max(int(limit), 0)])


def build_column_names_sql(
    domain: SemanticCoverageDomain,
    *,
    groups: Optional[Sequence[Tuple[str, str]]] = None,
) -> str:
    """生成「源表真实列名」的采集 SQL(纯函数, 便于单测断言)。

    用 ``jsonb_object_keys(raw_data)`` 把 ``raw_data`` 的**真实键**取出来 ——
    这就是运维在源表里看到的列名(原样, 不做归一化)。

    Args:
        domain: 语义域定义。
        groups: 只采集这些 ``(platform_code, granularity)`` 组;
            为空则采集全部组。
    """
    where_clause = ""
    if groups:
        literals = ", ".join(
            "('{}', '{}')".format(
                str(platform).replace("'", "''"),
                str(granularity).replace("'", "''"),
            )
            for platform, granularity in sorted(groups)
        )
        where_clause = f"WHERE (s.platform_code, s.granularity) IN ({literals})"
    return f"""
        WITH column_keys AS (
            SELECT DISTINCT
                s.platform_code,
                s.granularity,
                k.column_name
            FROM {domain.relation} s
            CROSS JOIN LATERAL jsonb_object_keys(
                CASE
                    WHEN s.raw_data IS NULL OR s.raw_data = '{{}}'::jsonb
                        THEN '{{}}'::jsonb
                    ELSE s.raw_data
                END
            ) AS k(column_name)
            {where_clause}
        )
        SELECT
            platform_code,
            granularity,
            array_agg(column_name ORDER BY column_name) AS column_names
        FROM column_keys
        GROUP BY platform_code, granularity
        ORDER BY platform_code, granularity
    """


def _resolved_column_name(standard_field: str) -> str:
    return f"resolved_{standard_field}"


def _column_expression(field: SemanticCoverageField) -> str:
    """column 模式: 该列"有值"的判定表达式。"""
    if field.kind == FIELD_KIND_NUMERIC:
        # 数值列: NULL 才算没解析出来(0 是合法值)。
        return f"{field.source} IS NOT NULL"
    # 文本列: 空串也算没解析出来。
    return f"NULLIF(TRIM({field.source}), '') IS NOT NULL"


def build_coverage_sql(domain: SemanticCoverageDomain) -> str:
    """生成某个语义域的覆盖率聚合 SQL(纯函数, 便于单测断言口径)。

    输出列(每个 平台 × 粒度 一行):
    ``platform_code`` / ``granularity`` / ``total_rows`` /
    ``empty_shell_rows`` / ``all_unresolved_rows`` / ``resolved_<字段名>``...
    """
    if domain.resolution_mode == RESOLUTION_MODE_ALIAS:
        return _build_alias_coverage_sql(domain)
    return _build_column_coverage_sql(domain)


def _build_alias_coverage_sql(domain: SemanticCoverageDomain) -> str:
    """alias 模式: 用 ``semantic.resolve_alias()`` 复算解析率。

    这条路径与 ``semantic.fact_products_atomic`` 的取值路径一致 ⇒
    视图侧的 ``COALESCE(..., 0)`` 不会把解析失败伪装成成功。
    """
    lateral_columns = ",\n                ".join(
        "semantic.resolve_alias(s.raw_data, s.data_domain, "
        f"'{field.source}', s.platform_code, s.granularity) AS c_{field.standard_field}"
        for field in domain.fields
    )
    resolved_columns = ",\n        ".join(
        f"SUM(CASE WHEN c_{field.standard_field} IS NOT NULL THEN 1 ELSE 0 END) "
        f"AS {_resolved_column_name(field.standard_field)}"
        for field in domain.fields
    )
    any_resolved = " OR ".join(
        f"c_{field.standard_field} IS NOT NULL" for field in domain.fields
    )
    carried_columns = ",\n                ".join(
        f"r.c_{field.standard_field}" for field in domain.fields
    )
    return f"""
        WITH scoped AS (
            SELECT
                platform_code,
                granularity,
                data_domain,
                raw_data,
                CASE WHEN raw_data IS NULL OR raw_data = '{{}}'::jsonb THEN 1 ELSE 0 END AS is_empty_shell
            FROM {domain.relation}
        ),
        resolved AS (
            SELECT
                s.platform_code,
                s.granularity,
                s.is_empty_shell,
                {carried_columns}
            FROM scoped s
            CROSS JOIN LATERAL (
                SELECT
                {lateral_columns}
            ) r
        )
        SELECT
            platform_code,
            granularity,
            COUNT(*) AS total_rows,
            SUM(is_empty_shell) AS empty_shell_rows,
            SUM(CASE WHEN ({any_resolved}) THEN 0 ELSE 1 END) AS all_unresolved_rows,
            {resolved_columns}
        FROM resolved
        GROUP BY platform_code, granularity
        ORDER BY platform_code, granularity
    """


def _build_column_coverage_sql(domain: SemanticCoverageDomain) -> str:
    """column 模式: 直接按视图列的 NULL 性判定。"""
    resolved_columns = ",\n        ".join(
        f"SUM(CASE WHEN ({_column_expression(field)}) THEN 1 ELSE 0 END) "
        f"AS {_resolved_column_name(field.standard_field)}"
        for field in domain.fields
    )
    any_resolved = " OR ".join(
        f"({_column_expression(field)})" for field in domain.fields
    )
    return f"""
        SELECT
            platform_code,
            granularity,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN raw_data IS NULL OR raw_data = '{{}}'::jsonb THEN 1 ELSE 0 END) AS empty_shell_rows,
            SUM(CASE WHEN ({any_resolved}) THEN 0 ELSE 1 END) AS all_unresolved_rows,
            {resolved_columns}
        FROM {domain.relation}
        GROUP BY platform_code, granularity
        ORDER BY platform_code, granularity
    """


def _to_int(value: Any) -> int:
    """把聚合结果(可能是 Decimal/NULL)转成 int。"""
    if value is None:
        return 0
    return int(value)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def build_coverage_report(
    rows: Iterable[Mapping[str, Any]],
    *,
    domain: SemanticCoverageDomain,
    threshold: float = DEFAULT_RESOLUTION_THRESHOLD,
    column_candidates: Optional[Mapping[Tuple[str, str], Sequence[str]]] = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> SemanticCoverageReport:
    """把聚合结果整成报告(纯函数, 不碰数据库)。

    口径:
    * ``payload_rows`` = 总行数 - 空壳行 —— 解析率的分母。
    * ``unresolved_rows`` = 有内容但**整行没有任何标准字段**解析成功 —— 真正的映射缺失。
    * 解析率 < 阈值 ⇒ 产生 warning; 空壳行不参与分母 ⇒ 不产生解析缺失告警。
    * 解析率 **0%** ⇒ 额外给出**源表真实列名候选**(见 ``column_candidates``),
      让人一眼看出「源表到底叫啥」。

    Args:
        rows: 聚合结果行。
        domain: 语义域定义(决定字段集合与别名来源)。
        threshold: 解析率告警阈值。
        column_candidates: ``(平台, 粒度)`` → 源表真实列名序列。
        candidate_limit: 每个字段最多给出多少个候选。
    """
    entries: List[SemanticCoverageEntry] = []
    groups: List[SemanticCoverageGroup] = []
    warnings: List[str] = []
    empty_shell_total = 0
    unresolved_total = 0
    candidate_map: Dict[str, Tuple[str, ...]] = {}
    candidates_by_group = dict(column_candidates or {})

    for row in rows:
        platform_code = str(row.get("platform_code") or "")
        granularity = str(row.get("granularity") or "")
        total_rows = _to_int(row.get("total_rows"))
        empty_shell_rows = _to_int(row.get("empty_shell_rows"))
        all_unresolved_rows = _to_int(row.get("all_unresolved_rows"))

        # 空壳行必然"整行都没解析出来" ⇒ 从 unresolved 里剔除, 单独计数。
        payload_rows = max(total_rows - empty_shell_rows, 0)
        unresolved_rows = max(all_unresolved_rows - empty_shell_rows, 0)
        empty_shell_total += empty_shell_rows
        unresolved_total += unresolved_rows

        groups.append(
            SemanticCoverageGroup(
                platform_code=platform_code,
                granularity=granularity,
                total_rows=total_rows,
                empty_shell_rows=empty_shell_rows,
                payload_rows=payload_rows,
                unresolved_rows=unresolved_rows,
                unresolved_rate=_rate(unresolved_rows, payload_rows),
            )
        )

        if payload_rows <= 0:
            # 这一组全是空壳行 ⇒ 没有可判定的数据, 不进解析率, 也不告警。
            continue

        group_columns = candidates_by_group.get((platform_code, granularity), ())
        for field_spec in domain.fields:
            resolved_rows = _to_int(
                row.get(_resolved_column_name(field_spec.standard_field))
            )
            resolution_rate = _rate(resolved_rows, payload_rows)
            entries.append(
                SemanticCoverageEntry(
                    platform_code=platform_code,
                    granularity=granularity,
                    standard_field=field_spec.standard_field,
                    resolved_rows=resolved_rows,
                    total_rows=payload_rows,
                    resolution_rate=resolution_rate,
                )
            )
            if resolution_rate >= threshold:
                continue

            candidates: Tuple[str, ...] = ()
            if resolution_rate <= 0 and group_columns:
                candidates = _rank_column_candidates(
                    field_spec.standard_field,
                    group_columns,
                    domain_name=domain.name,
                    platform_code=platform_code,
                    limit=candidate_limit,
                )
            if candidates:
                candidate_key = (
                    f"{platform_code}/{granularity}/{field_spec.standard_field}"
                )
                candidate_map[candidate_key] = candidates
                warnings.append(
                    f"{platform_code}/{granularity} 的 {field_spec.standard_field} "
                    f"解析率 {resolution_rate:.0%}，疑似语义映射缺失"
                    "（疑似列名未登记）；源表实际列名候选：" + " / ".join(candidates)
                )
            elif resolution_rate <= 0:
                # 解析率 0% ⇒ 列名大概率没登记(也可能源表压根没这一列)。
                warnings.append(
                    f"{platform_code}/{granularity} 的 {field_spec.standard_field} "
                    f"解析率 {resolution_rate:.0%}，疑似语义映射缺失"
                    "（疑似列名未登记）"
                )
            else:
                # 0 < 解析率 < 阈值 ⇒ 列名是登记了的, 只是没覆盖到全部行。
                warnings.append(
                    f"{platform_code}/{granularity} 的 {field_spec.standard_field} "
                    f"解析率 {resolution_rate:.0%}，疑似语义映射缺失"
                )

        unresolved_rate = _rate(unresolved_rows, payload_rows)
        if unresolved_rate >= threshold:
            warnings.append(
                f"{platform_code}/{granularity} 有 {unresolved_rate:.0%} 的数据行"
                "未解析出任何标准字段，疑似语义映射缺失"
            )

    platforms = _build_platform_summaries(entries, domain.name)
    for summary in platforms:
        if summary.zero_fields <= 0:
            continue
        warnings.append(
            f"{summary.platform_code} 平台有 {summary.zero_fields}/"
            f"{summary.total_fields} 个标准字段在所有粒度下都解析不出来，"
            "疑似语义映射缺失"
        )

    return SemanticCoverageReport(
        entries=tuple(entries),
        empty_shell_rows=empty_shell_total,
        unresolved_rows=unresolved_total,
        warnings=tuple(warnings),
        groups=tuple(groups),
        domain=domain.name,
        threshold=threshold,
        column_candidates=candidate_map,
        platforms=tuple(platforms),
    )


def _build_platform_summaries(
    entries: Sequence[SemanticCoverageEntry],
    domain: str = "orders",
) -> List[SemanticCoveragePlatformSummary]:
    """按平台汇总(阶段 5.3: 平台维度诊断)。

    * ``total_fields``: 该平台**适用**的标准字段数(跨粒度去重);
    * ``zero_fields``: 该平台下**所有粒度都**解析率为 0 的标准字段数 ——
      这种字段通常意味着「源表压根没有这一列 / 列名没登记」。

    ⚠ **按平台适用性过滤**(2026-11-08): 有的标准字段**只有部分平台有对应源列**
    (例: ``total_income`` 只有 tiktok 有, shopee 侧的对应概念是结算口径的
    「预估回款金额 / 已结算金额」)。不过滤 ⇒ shopee 会被报「缺 total_income」
    = **噪音**, 反而掩盖真实缺口。
    判定依据是字典里的 ``platforms`` 语义属性 ⇒ 未标 ``platforms`` 的字段
    (跨平台通用语义, 如 ``platform_service_fee``)仍然照常纳入诊断。
    """
    fields_by_platform: Dict[str, set[str]] = {}
    rates_by_platform: Dict[str, Dict[str, List[float]]] = {}
    for entry in entries:
        fields_by_platform.setdefault(entry.platform_code, set()).add(
            entry.standard_field
        )
        rates_by_platform.setdefault(entry.platform_code, {}).setdefault(
            entry.standard_field, []
        ).append(entry.resolution_rate)

    summaries: List[SemanticCoveragePlatformSummary] = []
    for platform_code in sorted(fields_by_platform):
        applicable = platform_applicable_fields(domain, platform_code)
        total_fields = len(fields_by_platform[platform_code] & applicable)
        # 「所有粒度都 0%」⇒ 该字段在这个平台上一次都没解析出来。
        always_zero = sorted(
            field
            for field, rates in rates_by_platform[platform_code].items()
            if all(rate <= 0 for rate in rates) and field in applicable
        )
        summaries.append(
            SemanticCoveragePlatformSummary(
                platform_code=platform_code,
                total_fields=total_fields,
                zero_fields=len(always_zero),
                zero_rate=_rate(len(always_zero), total_fields),
                zero_standard_fields=tuple(always_zero),
            )
        )
    return summaries


def _skipped_report(
    spec: SemanticCoverageDomain,
    domain: str,
    threshold: float,
    exc: BaseException,
) -> SemanticCoverageReport:
    """查询失败时的兜底报告: 空 entries + 一条 warning。

    巡检本身**绝不能**把调用方带崩 —— 失败也要留痕(调用方据此报警)。
    """
    return SemanticCoverageReport(
        entries=(),
        empty_shell_rows=0,
        unresolved_rows=0,
        warnings=(
            f"语义覆盖率巡检跳过：{spec.relation} 不可用或查询失败"
            f"（{type(exc).__name__}）。",
        ),
        domain=domain,
        threshold=threshold,
    )


class SemanticCoverageAuditService:
    """语义覆盖率巡检服务(纯读)。"""

    def __init__(
        self,
        *,
        threshold: float = DEFAULT_RESOLUTION_THRESHOLD,
        domains: Optional[Mapping[str, SemanticCoverageDomain]] = None,
    ) -> None:
        self._threshold = threshold
        self._domains = dict(domains or SEMANTIC_COVERAGE_DOMAINS)

    @property
    def threshold(self) -> float:
        return self._threshold

    def available_domains(self) -> Tuple[str, ...]:
        return tuple(sorted(self._domains))

    async def audit(
        self,
        db: AsyncSession,
        *,
        domain: str = "products",
        threshold: Optional[float] = None,
    ) -> SemanticCoverageReport:
        """对某个语义域做一次覆盖率巡检。

        异常一律吞掉: 返回**空报告 + 一条 warning**, 不让巡检把调用方带崩。
        """
        spec = self._domains.get(domain)
        if spec is None:
            return SemanticCoverageReport(
                entries=(),
                empty_shell_rows=0,
                unresolved_rows=0,
                warnings=(f"未知的语义覆盖域：{domain}",),
                domain=domain,
                threshold=self._threshold if threshold is None else threshold,
            )

        effective_threshold = self._threshold if threshold is None else threshold
        sql = build_coverage_sql(spec)

        # ⚠️ 必须容错: ``semantic.fact_*_atomic`` 是 raw SQL 层(sql/semantic/*.sql),
        # 不在 Base.metadata 里 —— 没有 semantic schema 的库上裸查会抛 ProgrammingError。
        #
        # ⚠️⚠️ **不能用「try/except 包住裸查」来容错**: PostgreSQL 里一条语句失败会让
        # **整个事务进入 aborted 状态**, 后续所有语句都抛 InFailedSQLTransactionError ⇒
        # 不是这里返回空报告, 而是整个调用方在后面某处 500。
        #
        # 正确做法(两步, 与 backend/services/inventory/inventory_age_query_service.py 一致):
        # 1. 先用 to_regclass 探测视图是否存在 —— 不存在就**根本不发出会失败的查询**;
        # 2. 万一视图存在但查询仍失败(列改名、权限不足等), 用 db.begin_nested()
        #    开一个 SAVEPOINT 包住它, 异常时只回滚到保存点, 外层事务仍然可用。
        try:
            exists = await db.execute(
                text("SELECT to_regclass(:relation) AS oid"),
                {"relation": spec.relation},
            )
            relation_oid = exists.mappings().one()["oid"]
        except SQLAlchemyError as exc:
            logger.warning(
                "[SemanticCoverage] 语义覆盖率巡检跳过（%s / %s，探测失败）: %s",
                domain,
                spec.relation,
                exc,
            )
            return _skipped_report(spec, domain, effective_threshold, exc)

        if relation_oid is None:
            logger.warning(
                "[SemanticCoverage] 语义覆盖率巡检跳过（%s / %s 不存在）",
                domain,
                spec.relation,
            )
            return SemanticCoverageReport(
                entries=(),
                empty_shell_rows=0,
                unresolved_rows=0,
                warnings=(
                    f"语义覆盖率巡检跳过：{spec.relation} 不存在"
                    "（可能尚未部署 semantic 视图）。",
                ),
                domain=domain,
                threshold=effective_threshold,
            )

        try:
            async with db.begin_nested():
                result = await db.execute(text(sql))
                rows = list(result.mappings().all())
        except SQLAlchemyError as exc:
            logger.warning(
                "[SemanticCoverage] 语义覆盖率巡检跳过（%s / %s）: %s",
                domain,
                spec.relation,
                exc,
            )
            return _skipped_report(spec, domain, effective_threshold, exc)

        report = build_coverage_report(
            rows,
            domain=spec,
            threshold=effective_threshold,
        )

        # 只有「确实有字段解析率为 0%」才需要去采真实列名 ——
        # 少一次全表扫描(源表行数大时这一步不便宜)。
        zero_groups = {
            (entry.platform_code, entry.granularity)
            for entry in report.entries
            if entry.resolution_rate <= 0
        }
        if not zero_groups:
            return report

        column_names = await self._fetch_column_names(db, spec, zero_groups)
        if not column_names:
            return report

        return build_coverage_report(
            rows,
            domain=spec,
            threshold=effective_threshold,
            column_candidates=column_names,
        )

    async def _fetch_column_names(
        self,
        db: AsyncSession,
        spec: SemanticCoverageDomain,
        groups: Sequence[Tuple[str, str]],
    ) -> Dict[Tuple[str, str], Tuple[str, ...]]:
        """采集源表**真实列名**(按 平台 × 粒度)。

        只发 SELECT; 失败时只记 warning 并返回空字典 ——
        候选列名是**锦上添花**, 拿不到也不该让整次巡检失败。
        """
        sql = build_column_names_sql(spec, groups=groups)
        try:
            async with db.begin_nested():
                result = await db.execute(text(sql))
                rows = list(result.mappings().all())
        except Exception as exc:  # noqa: BLE001 —— 巡检绝不能把调用方带崩
            logger.warning(
                "[SemanticCoverage] 真实列名采集失败（%s / %s）: %s",
                spec.name,
                spec.relation,
                exc,
            )
            return {}

        column_names: Dict[Tuple[str, str], Tuple[str, ...]] = {}
        for row in rows:
            platform_code = str(row.get("platform_code") or "")
            granularity = str(row.get("granularity") or "")
            names = row.get("column_names") or ()
            if isinstance(names, str):
                names = (names,)
            column_names[(platform_code, granularity)] = tuple(
                str(name) for name in names
            )
        return column_names
