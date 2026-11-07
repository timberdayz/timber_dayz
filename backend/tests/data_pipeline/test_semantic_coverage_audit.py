"""语义层覆盖率巡检服务的测试。

覆盖四件事（对应任务验收口径）：
1. 解析率正常的域 **不** 产生 warning；
2. 解析率 0% 产生 warning（平台, 粒度, 标准字段 三元组 + 中文描述）；
3. **空壳行**（raw_data 为空对象）被单独计数，且 **不** 产生"解析缺失"告警
   —— 空壳行是"入库没拿到数据"，与"有 raw_data 但解析不出来"必须分开处置；
4. 表/视图不存在时安全返回**空报告 + 一条 warning**，不把调用方带崩。

测试用两种方式：
* 纯函数层（``build_coverage_report``）：用假数据精确验证口径，不碰数据库；
* 服务层（``SemanticCoverageAuditService.audit``）：用假 session 验证
  "视图不存在 → 空报告 + 一条 warning"这条容错路径。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pytest
from sqlalchemy.exc import ProgrammingError

from backend.services.semantic_coverage_audit_service import (
    DEFAULT_RESOLUTION_THRESHOLD,
    ORDERS_STANDARD_FIELDS,
    PRODUCTS_STANDARD_FIELDS,
    SEMANTIC_COVERAGE_DOMAINS,
    SemanticCoverageAuditService,
    SemanticCoverageDomain,
    SemanticCoverageField,
    build_coverage_report,
    build_coverage_sql,
)


# ── 假 session ────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows: Iterable[Dict[str, Any]]) -> None:
        self._rows = list(rows)

    def mappings(self) -> "_FakeResult":
        return self

    def one(self) -> Dict[str, Any]:
        return self._rows[0]

    def all(self) -> List[Dict[str, Any]]:
        return list(self._rows)


class _FakeSession:
    """按 SQL 关键字返回预置结果的假 session。

    ``relation_missing=True`` 时, 视图探测(to_regclass)返回 NULL,
    模拟"库里没有 semantic 视图"。
    """

    def __init__(
        self,
        *,
        rows: Optional[List[Dict[str, Any]]] = None,
        relation_missing: bool = False,
        raise_on_query: Optional[Exception] = None,
    ) -> None:
        self._rows = list(rows or [])
        self._relation_missing = relation_missing
        self._raise_on_query = raise_on_query
        self.statements: List[str] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if "to_regclass" in sql:
            return _FakeResult([{"oid": None if self._relation_missing else "16400"}])
        if self._raise_on_query is not None:
            raise self._raise_on_query
        return _FakeResult(self._rows)

    def begin_nested(self) -> "_FakeNested":
        return _FakeNested()


class _FakeNested:
    async def __aenter__(self) -> "_FakeNested":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


# ── 构造聚合结果行 ────────────────────────────────────────────────────


def _row(
    platform_code: str,
    granularity: str,
    *,
    total_rows: int,
    empty_shell_rows: int = 0,
    all_unresolved_rows: int = 0,
    resolved: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """造一行聚合结果（``resolved`` 省略的字段按 0 处理）。"""
    row: Dict[str, Any] = {
        "platform_code": platform_code,
        "granularity": granularity,
        "total_rows": total_rows,
        "empty_shell_rows": empty_shell_rows,
        "all_unresolved_rows": all_unresolved_rows,
    }
    for field in PRODUCTS_STANDARD_FIELDS:
        row[f"resolved_{field.standard_field}"] = int(
            (resolved or {}).get(field.standard_field, 0)
        )
    return row


def _all_resolved(total_rows: int, **overrides: int) -> Dict[str, int]:
    """默认"所有标准字段都解析成功"，再按需覆盖个别字段。"""
    resolved = {field.standard_field: total_rows for field in PRODUCTS_STANDARD_FIELDS}
    resolved.update(overrides)
    return resolved


def _products_domain() -> SemanticCoverageDomain:
    return SEMANTIC_COVERAGE_DOMAINS["products"]


# ── 1. 解析率正常的域不产生 warning ───────────────────────────────────


def test_healthy_domain_produces_no_warning():
    """所有标准字段都解析成功 ⇒ 没有 warning。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved={field.standard_field: 100 for field in PRODUCTS_STANDARD_FIELDS},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    assert report.warnings == ()
    assert report.unresolved_rows == 0
    assert report.empty_shell_rows == 0
    assert len(report.entries) == len(PRODUCTS_STANDARD_FIELDS)
    for entry in report.entries:
        assert entry.resolved_rows == 100
        assert entry.total_rows == 100
        assert entry.resolution_rate == 1.0


def test_entry_resolution_rate_is_computed_per_platform_and_granularity():
    """解析率按 (平台 × 粒度 × 标准字段) 分组统计。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=200,
            resolved={"sales_amount": 150, "product_id": 200},
        ),
        _row(
            "tiktok",
            "daily",
            total_rows=50,
            resolved={"sales_amount": 50, "product_id": 50},
        ),
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    by_key = {
        (entry.platform_code, entry.granularity, entry.standard_field): entry
        for entry in report.entries
    }
    shopee_sales = by_key[("shopee", "monthly", "sales_amount")]
    assert shopee_sales.resolved_rows == 150
    assert shopee_sales.total_rows == 200
    assert shopee_sales.resolution_rate == 0.75

    tiktok_sales = by_key[("tiktok", "daily", "sales_amount")]
    assert tiktok_sales.resolution_rate == 1.0

    # shopee 的 clicks 一次都没解析出来 ⇒ 0%。
    assert by_key[("shopee", "monthly", "clicks")].resolution_rate == 0.0


# ── 2. 解析率 0% 产生 warning ─────────────────────────────────────────


def test_zero_resolution_rate_produces_warning_with_chinese_description():
    """解析率 0% ⇒ 产生 (平台, 粒度, 标准字段) 三元组告警 + 中文描述。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=25810,
            resolved={"product_id": 25810, "product_name": 25810},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    assert report.warnings, "解析率 0% 的字段必须产生 warning"

    sales_warnings = [w for w in report.warnings if "sales_amount" in w]
    assert sales_warnings, "sales_amount 解析率 0% 必须被点名"
    warning = sales_warnings[0]
    assert "shopee/monthly" in warning
    assert "解析率 0%" in warning
    assert "疑似语义映射缺失" in warning

    # 只有真正为 0% 的字段才告警 —— 解析成功的字段不该被点名。
    assert not [w for w in report.warnings if "product_id " in w]


def test_warning_threshold_is_parameterizable():
    """阈值可参数化：调低阈值后，原本达标的字段不再告警。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved=_all_resolved(100, sales_amount=80),
        )
    ]

    default_report = build_coverage_report(
        rows, domain=_products_domain(), threshold=DEFAULT_RESOLUTION_THRESHOLD
    )
    assert default_report.warnings == ()

    strict_report = build_coverage_report(
        rows, domain=_products_domain(), threshold=0.9
    )
    assert strict_report.warnings
    assert any("sales_amount" in w for w in strict_report.warnings)


@pytest.mark.asyncio
async def test_service_reads_threshold_from_constructor_and_call_site():
    """构造函数阈值 + 调用点覆盖，两者都要生效。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved=_all_resolved(100, sales_amount=80),
        )
    ]
    service = SemanticCoverageAuditService(threshold=0.9)
    assert service.threshold == 0.9
    assert service.available_domains() == ("orders", "products")

    # 调用点覆盖成 0.5 ⇒ sales_amount(80%)不再告警。
    report = await service.audit(
        _FakeSession(rows=rows), domain="products", threshold=0.5
    )
    assert report.warnings == ()
    assert report.threshold == 0.5

    # 构造函数阈值 0.9 生效 ⇒ sales_amount(80%)告警。
    strict_report = await service.audit(_FakeSession(rows=rows), domain="products")
    assert strict_report.warnings
    assert any("sales_amount" in w for w in strict_report.warnings)


# ── 3. 空壳行单独计数，且不产生"解析缺失"告警 ─────────────────────────


def test_empty_shell_rows_are_counted_separately_and_do_not_warn():
    """空壳行(raw_data 为空对象)单独计数，不进解析率分母，也不触发解析缺失告警。

    这两类必须分开：
    * 空壳行 = 入库时根本没拿到数据 ⇒ 该重跑采集；
    * 有 raw_data 但解析不出来 = 语义映射缺失 ⇒ 该补别名。
    """
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=10204,
            empty_shell_rows=10204,
            all_unresolved_rows=10204,
            resolved={field.standard_field: 0 for field in PRODUCTS_STANDARD_FIELDS},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    # 空壳行被单独计数。
    assert report.empty_shell_rows == 10204
    # 空壳行不算"有 raw_data 但解析不出来"。
    assert report.unresolved_rows == 0
    # 不产生"解析缺失"告警。
    assert report.warnings == ()
    # 整组都是空壳行 ⇒ 没有可判定的数据 ⇒ 不产出解析率条目。
    assert report.entries == ()

    group = report.groups[0]
    assert group.total_rows == 10204
    assert group.empty_shell_rows == 10204
    assert group.payload_rows == 0
    assert group.unresolved_rows == 0


def test_empty_shell_rows_are_excluded_from_resolution_rate_denominator():
    """混合场景：空壳行不占分母，解析率只反映"真的拿到了数据"的那些行。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=300,
            empty_shell_rows=100,
            all_unresolved_rows=100,
            resolved={field.standard_field: 200 for field in PRODUCTS_STANDARD_FIELDS},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    assert report.empty_shell_rows == 100
    entry = next(e for e in report.entries if e.standard_field == "product_id")
    # 分母是 300 - 100 = 200（排除空壳行）。
    assert entry.total_rows == 200
    assert entry.resolved_rows == 200
    assert entry.resolution_rate == 1.0
    assert report.warnings == ()


def test_rows_with_payload_but_no_parsed_field_are_reported_as_unresolved():
    """有 raw_data 但一个标准字段都没解析出来 ⇒ 计入 unresolved 并告警。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=100,
            empty_shell_rows=0,
            all_unresolved_rows=100,
            resolved={},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    assert report.empty_shell_rows == 0
    assert report.unresolved_rows == 100
    assert report.warnings
    assert any("未解析出任何标准字段" in w for w in report.warnings)


def test_empty_shell_and_unresolved_are_distinguished_in_the_same_group():
    """同一组里两类同时存在时，计数必须分开。"""
    rows = [
        _row(
            "shopee",
            "monthly",
            total_rows=1000,
            empty_shell_rows=10204 - 10000,
            all_unresolved_rows=1000,
            resolved={field.standard_field: 900 for field in PRODUCTS_STANDARD_FIELDS},
        )
    ]

    report = build_coverage_report(rows, domain=_products_domain())

    assert report.empty_shell_rows == 204
    # 1000 行整行没解析出来，其中 204 行是空壳 ⇒ 真正的"有数据但解析不出"是 796 行。
    assert report.unresolved_rows == 796
    group = report.groups[0]
    assert group.payload_rows == 796
    assert group.unresolved_rows == 796
    assert group.unresolved_rate == 1.0


# ── 4. 表/视图不存在 ⇒ 空报告 + 一条 warning ──────────────────────────


@pytest.mark.asyncio
async def test_missing_relation_returns_empty_report_with_single_warning():
    """没有 semantic 视图的库 ⇒ 空报告 + 一条 warning，不抛异常。"""
    session = _FakeSession(relation_missing=True)

    report = await SemanticCoverageAuditService().audit(session, domain="products")

    assert report.entries == ()
    assert report.groups == ()
    assert report.empty_shell_rows == 0
    assert report.unresolved_rows == 0
    assert len(report.warnings) == 1
    assert "semantic.fact_products_atomic" in report.warnings[0]
    assert "不存在" in report.warnings[0]


@pytest.mark.asyncio
async def test_query_failure_returns_empty_report_and_does_not_raise():
    """查询失败(列改名/权限不足等)⇒ 空报告 + 一条 warning，异常不外泄。"""
    session = _FakeSession(
        raise_on_query=ProgrammingError("SELECT 1", {}, Exception("boom"))
    )

    report = await SemanticCoverageAuditService().audit(session, domain="products")

    assert report.entries == ()
    assert len(report.warnings) == 1
    assert "跳过" in report.warnings[0]


@pytest.mark.asyncio
async def test_unknown_domain_returns_warning_instead_of_raising():
    """未知域 ⇒ 明确告警，而不是抛 KeyError。"""
    report = await SemanticCoverageAuditService().audit(
        _FakeSession(), domain="not_a_domain"
    )

    assert report.entries == ()
    assert len(report.warnings) == 1
    assert "not_a_domain" in report.warnings[0]


@pytest.mark.asyncio
async def test_audit_is_read_only_and_probes_relation_before_querying():
    """纯读：只发 SELECT；先探测视图存在再发聚合查询。"""
    session = _FakeSession(rows=[])

    await SemanticCoverageAuditService().audit(session, domain="products")

    assert session.statements, "巡检必须发出查询"
    assert "to_regclass" in session.statements[0], "必须先探测视图是否存在"
    for sql in session.statements:
        assert "INSERT" not in sql.upper()
        assert "UPDATE" not in sql.upper()
        assert "DELETE" not in sql.upper()


# ── SQL 口径 ──────────────────────────────────────────────────────────


def test_products_sql_uses_alias_resolution_not_coalesced_view_columns():
    """商品域必须走 resolve_alias —— 否则视图的 COALESCE(...,0) 会把失败伪装成成功。"""
    sql = build_coverage_sql(_products_domain())

    assert "semantic.resolve_alias(" in sql
    assert "semantic.fact_products_atomic" in sql
    for field in PRODUCTS_STANDARD_FIELDS:
        assert f"'{field.standard_field}'" in sql
        assert f"resolved_{field.standard_field}" in sql
    # 不能直接拿视图里被 COALESCE 掩盖的数值列当解析结果。
    assert "COALESCE(sales_amount" not in sql


def test_orders_sql_uses_null_preserving_view_columns():
    """订单域(对照域)按视图列的 NULL 性判定，不调用 resolve_alias。"""
    sql = build_coverage_sql(SEMANTIC_COVERAGE_DOMAINS["orders"])

    assert "semantic.fact_orders_atomic" in sql
    assert "semantic.resolve_alias(" not in sql
    # 被 COALESCE(...,0) 掩盖的数值列不纳入订单域巡检。
    assert "sales_amount" not in sql
    assert "resolved_order_id" in sql


def test_empty_shell_detection_is_present_in_both_domains():
    """两个域都要能识别空壳行(raw_data 为空对象)。"""
    for domain in ("products", "orders"):
        sql = build_coverage_sql(SEMANTIC_COVERAGE_DOMAINS[domain])
        assert "empty_shell_rows" in sql
        assert "'{}'::jsonb" in sql


def test_orders_domain_excludes_coalesce_masked_numeric_columns():
    """订单域不得包含被 COALESCE(...,0) 掩盖、无法判定解析失败的列。"""
    masked = {
        "sales_amount",
        "paid_amount",
        "profit",
        "product_quantity",
        "buyer_count",
    }
    audited = {field.standard_field for field in ORDERS_STANDARD_FIELDS}

    assert not (audited & masked)
    # 保留 NULL 的列必须纳入。
    assert {"order_id", "product_id", "product_name", "purchase_amount"} <= audited


def test_custom_domain_can_be_injected():
    """域定义可注入（便于将来加域），且字段口径可自定义。"""
    custom = SemanticCoverageDomain(
        name="custom",
        relation="semantic.fact_custom_atomic",
        resolution_mode="column",
        fields=(SemanticCoverageField("foo", "foo", "text"),),
    )
    service = SemanticCoverageAuditService(domains={"custom": custom})

    assert service.available_domains() == ("custom",)
    sql = build_coverage_sql(custom)
    assert "semantic.fact_custom_atomic" in sql
    assert "resolved_foo" in sql
