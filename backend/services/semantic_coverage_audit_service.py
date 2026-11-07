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
* 商品域: 走 ``semantic.resolve_alias()`` —— 与视图里 ``semantic.fact_products_atomic``
  的取值路径**同一个函数**, 所以查出来的就是视图真正的解析口径。
  视图侧的 ``COALESCE(..., 0)`` 不会把失败伪装成成功。
* 订单域(对照域): 视图里这些列是按固定列名链取的, 且**保留 NULL**,
  因此直接按列的 NULL 性判定; 被 ``COALESCE(..., 0)`` 掩盖的数值列**不纳入**订单域巡检
  (它们无法区分"解析失败"与"真的是 0"), 避免给出假的"健康"结论。

只读保证
--------
本服务只发 SELECT, 不写库、不提交事务; 查询失败时吞掉异常并返回**空报告 + 一条 warning**,
绝不把调用方(定时任务/接口)带崩。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

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
class SemanticCoverageReport:
    """一次覆盖率巡检的结论。"""

    entries: Tuple[SemanticCoverageEntry, ...]
    empty_shell_rows: int
    unresolved_rows: int
    warnings: Tuple[str, ...]
    groups: Tuple[SemanticCoverageGroup, ...] = ()
    domain: str = ""
    threshold: float = DEFAULT_RESOLUTION_THRESHOLD
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── 被巡检的字段清单 ───────────────────────────────────────────────
#
# 商品域: 与 ``sql/semantic/products_atomic.sql`` 里走
# ``semantic.resolve_alias()`` 的标准字段**一一对应**
# (price/stock/page_views 这类走固定列名链的列不在巡检范围内)。
PRODUCTS_STANDARD_FIELDS: Tuple[SemanticCoverageField, ...] = (
    SemanticCoverageField("product_id", "product_id", FIELD_KIND_TEXT),
    SemanticCoverageField("product_name", "product_name", FIELD_KIND_TEXT),
    SemanticCoverageField("item_status", "item_status", FIELD_KIND_TEXT),
    SemanticCoverageField("order_count", "order_count", FIELD_KIND_NUMERIC),
    SemanticCoverageField("sales_amount", "sales_amount", FIELD_KIND_NUMERIC),
    SemanticCoverageField("sales_volume", "sales_volume", FIELD_KIND_NUMERIC),
    SemanticCoverageField("impressions", "impressions", FIELD_KIND_NUMERIC),
    SemanticCoverageField("clicks", "clicks", FIELD_KIND_NUMERIC),
    SemanticCoverageField("conversion_rate", "conversion_rate", FIELD_KIND_NUMERIC),
)

# 订单域(对照域): 只取视图里**保留 NULL** 的列。
# 被 ``COALESCE(..., 0)`` 掩盖的数值列(sales_amount/paid_amount/profit/
# product_quantity/buyer_count)无法区分"解析失败"与"真的是 0"⇒ 不纳入。
ORDERS_STANDARD_FIELDS: Tuple[SemanticCoverageField, ...] = (
    SemanticCoverageField("order_id", "order_id", FIELD_KIND_TEXT),
    SemanticCoverageField("order_status", "order_status", FIELD_KIND_TEXT),
    SemanticCoverageField("product_id", "product_id", FIELD_KIND_TEXT),
    SemanticCoverageField("platform_sku", "platform_sku", FIELD_KIND_TEXT),
    SemanticCoverageField("sku_id", "sku_id", FIELD_KIND_TEXT),
    SemanticCoverageField("product_sku", "product_sku", FIELD_KIND_TEXT),
    SemanticCoverageField("product_name", "product_name", FIELD_KIND_TEXT),
    SemanticCoverageField("purchase_amount", "purchase_amount", FIELD_KIND_NUMERIC),
    SemanticCoverageField(
        "order_original_amount", "order_original_amount", FIELD_KIND_NUMERIC
    ),
    SemanticCoverageField(
        "warehouse_operation_fee", "warehouse_operation_fee", FIELD_KIND_NUMERIC
    ),
    SemanticCoverageField("shipping_fee", "shipping_fee", FIELD_KIND_NUMERIC),
    SemanticCoverageField("promotion_fee", "promotion_fee", FIELD_KIND_NUMERIC),
    SemanticCoverageField(
        "platform_commission", "platform_commission", FIELD_KIND_NUMERIC
    ),
    SemanticCoverageField(
        "platform_deduction_fee", "platform_deduction_fee", FIELD_KIND_NUMERIC
    ),
    SemanticCoverageField("platform_voucher", "platform_voucher", FIELD_KIND_NUMERIC),
    SemanticCoverageField(
        "platform_service_fee", "platform_service_fee", FIELD_KIND_NUMERIC
    ),
)


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
        resolution_mode=RESOLUTION_MODE_COLUMN,
        fields=ORDERS_STANDARD_FIELDS,
    ),
}


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
) -> SemanticCoverageReport:
    """把聚合结果整成报告(纯函数, 不碰数据库)。

    口径:
    * ``payload_rows`` = 总行数 - 空壳行 —— 解析率的分母。
    * ``unresolved_rows`` = 有内容但**整行没有任何标准字段**解析成功 —— 真正的映射缺失。
    * 解析率 < 阈值 ⇒ 产生 warning; 空壳行不参与分母 ⇒ 不产生解析缺失告警。
    """
    entries: List[SemanticCoverageEntry] = []
    groups: List[SemanticCoverageGroup] = []
    warnings: List[str] = []
    empty_shell_total = 0
    unresolved_total = 0

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
            if resolution_rate < threshold:
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

    return SemanticCoverageReport(
        entries=tuple(entries),
        empty_shell_rows=empty_shell_total,
        unresolved_rows=unresolved_total,
        warnings=tuple(warnings),
        groups=tuple(groups),
        domain=domain.name,
        threshold=threshold,
    )


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

        return build_coverage_report(
            rows,
            domain=spec,
            threshold=effective_threshold,
        )
