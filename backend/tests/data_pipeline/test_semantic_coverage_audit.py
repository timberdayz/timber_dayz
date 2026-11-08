"""语义层覆盖率巡检服务的测试。

覆盖六件事（对应任务验收口径）：
1. 解析率正常的域 **不** 产生 warning；
2. 解析率 0% 产生 warning（平台, 粒度, 标准字段 三元组 + 中文描述）；
3. **空壳行**（raw_data 为空对象）被单独计数，且 **不** 产生"解析缺失"告警
   —— 空壳行是"入库没拿到数据"，与"有 raw_data 但解析不出来"必须分开处置；
4. 表/视图不存在时安全返回**空报告 + 一条 warning**，不把调用方带崩；
5. 解析率 0% 时给出**源表真实列名候选**（阶段 5.1）；
6. 字段清单**从字典派生**（阶段 5.2）+ 平台维度诊断（阶段 5.3）。

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
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_RESOLUTION_THRESHOLD,
    ORDERS_STANDARD_FIELDS,
    PRODUCTS_EXCLUDED_FIELDS,
    PRODUCTS_STANDARD_FIELDS,
    SEMANTIC_COVERAGE_DOMAINS,
    SemanticCoverageAuditService,
    SemanticCoverageDomain,
    SemanticCoverageField,
    build_column_names_sql,
    build_coverage_report,
    build_coverage_sql,
)
from backend.services.semantic_field_registry import (
    DOMAIN_SEMANTIC_ALIASES,
    ORDER_RETIRED_FIELDS,
    ORDER_STANDARD_FIELDS as REGISTRY_ORDER_STANDARD_FIELDS,
    platform_applicable_fields,
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
    fields: Optional[Iterable[SemanticCoverageField]] = None,
) -> Dict[str, Any]:
    """造一行聚合结果（``resolved`` 省略的字段按 0 处理）。"""
    row: Dict[str, Any] = {
        "platform_code": platform_code,
        "granularity": granularity,
        "total_rows": total_rows,
        "empty_shell_rows": empty_shell_rows,
        "all_unresolved_rows": all_unresolved_rows,
    }
    for field in fields if fields is not None else PRODUCTS_STANDARD_FIELDS:
        row[f"resolved_{field.standard_field}"] = int(
            (resolved or {}).get(field.standard_field, 0)
        )
    return row


def _all_resolved(
    total_rows: int,
    **overrides: int,
) -> Dict[str, int]:
    """默认"所有标准字段都解析成功"，再按需覆盖个别字段。"""
    resolved = {field.standard_field: total_rows for field in PRODUCTS_STANDARD_FIELDS}
    resolved.update(overrides)
    return resolved


def _orders_row(
    platform_code: str,
    granularity: str,
    *,
    total_rows: int,
    resolved: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """造一行**订单域**的聚合结果。"""
    return _row(
        platform_code,
        granularity,
        total_rows=total_rows,
        resolved=resolved,
        fields=ORDERS_STANDARD_FIELDS,
    )


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


def service_has_relation_resolver() -> bool:
    """服务层是否提供了「优先读物化视图」的 relation 解析。"""
    from backend.services.semantic_coverage_audit_service import (
        SemanticCoverageAuditService,
    )

    return hasattr(SemanticCoverageAuditService, "_resolve_relation")


# ── SQL 口径 ──────────────────────────────────────────────────────────


def test_products_sql_resolves_through_alias_registry_not_coalesced_view_columns():
    """商品域必须走**别名表** —— 否则视图的 COALESCE(...,0) 会把失败伪装成成功。

    [*] 2026-11-08 性能改造: 判定不再逐行逐字段调 ``semantic.resolve_alias()``
    (实测每次键访问约 23 微秒/行 => 整轮巡检 80~90 秒), 改成
    「一次展开 raw_data + 别名表哈希连接 + 数组重叠」⇒ 判定口径不变,
    耗时降一个数量级。

    ⇒ 守护从「用了 resolve_alias」改成更强的一组:
    (1) 走**别名表**(事实源仍然是同一张表);
    (2) **不再**逐行逐字段调 PL/pgSQL 函数(那是最慢的一环);
    (3) **一次展开** raw_data, 不逐键访问。
    """
    sql = build_coverage_sql(_products_domain())

    assert "semantic.semantic_field_aliases" in sql
    assert "semantic.resolve_alias(" not in sql
    assert "jsonb_each(" in sql
    assert "semantic.fact_products_atomic" in sql
    for field in PRODUCTS_STANDARD_FIELDS:
        assert f"'{field.standard_field}'" in sql
        assert f"resolved_{field.standard_field}" in sql
    # 不能直接拿视图里被 COALESCE 掩盖的数值列当解析结果。
    assert "COALESCE(sales_amount" not in sql


def test_orders_sql_resolves_through_alias_registry_not_coalesced_view_columns():
    """订单域也必须走**别名表** —— 视图的 COALESCE(...,0) 会把失败伪装成成功。

    阶段 5.2 口径变更：订单域从「按视图列的 NULL 性判定」改成「按别名解析」，
    这样被 COALESCE 掩盖的数值列才能区分「解析失败」与「真的是 0」。

    [*] 2026-11-08 性能改造: 判定实现换成集合式(见
    ``test_products_sql_resolves_through_alias_registry_not_coalesced_view_columns``),
    **口径不变** —— 仍然逐字按别名表匹配、仍然只把「值非空」算命中。
    """
    sql = build_coverage_sql(SEMANTIC_COVERAGE_DOMAINS["orders"])

    assert "semantic.fact_orders_atomic" in sql
    assert "semantic.semantic_field_aliases" in sql
    assert "semantic.resolve_alias(" not in sql
    assert "jsonb_each(" in sql
    for field in ORDERS_STANDARD_FIELDS:
        assert f"'{field.standard_field}'" in sql
        assert f"resolved_{field.standard_field}" in sql
    # 不能直接拿视图里被 COALESCE 掩盖的数值列当解析结果。
    assert "COALESCE(paid_amount" not in sql


def test_alias_mode_sql_keeps_resolution_criteria_explicit():
    """口径条件必须显式出现在 SQL 里(不能被优化掉)。

    这三条是「与 ``semantic.resolve_alias()`` 等价」的根据:

    1. 平台/粒度: 别名为空(通用)或与本行精确相同才是候选;
    2. 值非空才算命中(JSON null / 空串都不算);
    3. 只认 ``status = 'active'`` 的别名。
    """
    for domain in ("products", "orders"):
        sql = build_coverage_sql(SEMANTIC_COVERAGE_DOMAINS[domain])

        assert "status = 'active'" in sql
        assert "ar.platform_code = '' OR ar.platform_code = c.platform_code" in sql
        assert "ar.granularity = '' OR ar.granularity = c.granularity" in sql
        assert "k.value <> 'null'::jsonb" in sql
        assert "k.value <> '\"\"'::jsonb" in sql


def test_coverage_domains_prefer_materialized_view_when_available():
    """巡检**优先读物化视图**(MV 不存在时由服务层回退普通视图)。

    为什么: ``semantic.fact_*_atomic`` 是普通视图, 每次查询都要把整张视图
    重算一遍(订单域 3.6 万行 x 28 个标准字段的别名解析 + 数值清洗)
    ⇒ 实测单次聚合 80~90 秒, 慢到没法在看板里用。
    """
    for domain_name, mv_name in (
        ("orders", "semantic.fact_orders_atomic_mv"),
        ("products", "semantic.fact_products_atomic_mv"),
    ):
        spec = SEMANTIC_COVERAGE_DOMAINS[domain_name]
        assert spec.materialized_relation == mv_name
        assert spec.relation.endswith("_atomic")
        assert service_has_relation_resolver()


def test_empty_shell_detection_is_present_in_both_domains():
    """两个域都要能识别空壳行(raw_data 为空对象)。"""
    for domain in ("products", "orders"):
        sql = build_coverage_sql(SEMANTIC_COVERAGE_DOMAINS[domain])
        assert "empty_shell_rows" in sql
        assert "'{}'::jsonb" in sql


def test_orders_domain_field_set_is_derived_from_the_field_registry():
    """订单域巡检字段集合 == 字典的 ``ORDER_STANDARD_FIELDS``（阶段 5.2）。

    不再在本文件/服务里维护第 4 份手写清单 ⇒ 字典增删字段, 巡检自动跟随。
    """
    audited = {field.standard_field for field in ORDERS_STANDARD_FIELDS}

    assert audited == set(REGISTRY_ORDER_STANDARD_FIELDS)
    # 字典已废止的字段(sales_amount)不得回到巡检范围。
    assert not (audited & set(ORDER_RETIRED_FIELDS))
    # 被视图 COALESCE(...,0) 掩盖的数值列现在**要**纳入(走别名解析才能判定)。
    assert {"paid_amount", "profit", "buyer_count"} <= audited
    # 字典登记了、视图还没输出的字段也要能巡检。
    assert {"settled_amount", "seller_voucher", "refund_amount"} <= audited


def test_products_domain_field_set_is_derived_from_the_field_registry():
    """商品域巡检字段集合也来自字典（``DOMAIN_SEMANTIC_ALIASES["products"]``）。

    只减掉 :data:`PRODUCTS_EXCLUDED_FIELDS`（视图内计算列 / 下单口径字段）——
    视图内计算列在源表里压根没有这一列, 巡检它们永远是 0%, 只会刷屏假告警。
    """
    audited = {field.standard_field for field in PRODUCTS_STANDARD_FIELDS}
    registry_keys = set(DOMAIN_SEMANTIC_ALIASES["products"].keys())

    assert audited == registry_keys - set(PRODUCTS_EXCLUDED_FIELDS)
    # 视图内计算列不在范围内。
    assert "aov" not in audited
    assert "buyer_count" not in audited
    # 走 resolve_alias 的主干字段都在。
    assert {
        "product_id",
        "product_name",
        "item_status",
        "order_count",
        "sales_amount",
        "sales_volume",
        "impressions",
        "clicks",
        "conversion_rate",
    } <= audited


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


# ── 5. 解析率 0% ⇒ 给出源表真实列名候选（阶段 5.1） ─────────────────
#
# 场景取自开发库实测(2026-11): shopee 订单源表里有「联盟佣金(RMB)」,
# 但字典只登记了「Shopee平台佣金(RMB)」⇒ platform_commission 解析不出来。
# 巡检必须直接把「联盟佣金(RMB)」指出来, 而不是只说一句「解析率 0%」。

#: shopee 订单源表的真实列名(节选, 含已登记与未登记两类)。
SHOPEE_ORDER_COLUMNS: tuple[str, ...] = (
    "订单编号",
    "平台SKU",
    "联盟佣金(RMB)",
    "联盟佣金",
    "Shopee平台佣金(RMB)",
    "服务费(RMB)",
    "广告成本(RMB)",
    # 真实存在于 shopee 源表、但**字典未登记**的列(实测 2026-11 开发库)⇒
    # 它才是真正的「未登记候选」, 用来验证候选生成。
    "海外免退服务费(RMB)",
)


def _orders_domain() -> SemanticCoverageDomain:
    return SEMANTIC_COVERAGE_DOMAINS["orders"]


def test_zero_resolution_lists_real_source_column_candidates():
    """解析率 0% ⇒ 告警里必须出现**源表真实列名**候选。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(
        rows,
        domain=_orders_domain(),
        column_candidates={("shopee", "monthly"): SHOPEE_ORDER_COLUMNS},
    )

    fee_warnings = [w for w in report.warnings if "platform_service_fee" in w]
    assert fee_warnings, "platform_service_fee 解析率 0% 必须被点名"
    warning = fee_warnings[0]
    assert "解析率 0%" in warning
    assert "疑似语义映射缺失" in warning
    assert "疑似列名未登记" in warning
    assert "源表实际列名候选：" in warning
    # 候选里必须是**字典未登记**的真实列 —— 「海外免退服务费(RMB)」
    # (实测源表确有此列, 字典未登记)。
    assert "海外免退服务费(RMB)" in warning
    assert (
        "海外免退服务费(RMB)"
        in report.column_candidates["shopee/monthly/platform_service_fee"]
    )


def test_columns_registered_for_another_field_are_not_unregistered_candidates():
    """「已登记给**别的**字段」的列, 不是「列名未登记」的候选。

    「联盟佣金(RMB)」2026-11-08 起登记给 ``affiliate_commission``
    (联盟/达人佣金, 与平台佣金是两笔钱)⇒ 它**不再**是 platform_commission 的
    未登记候选 —— 否则巡检会把已经解决的问题继续报成缺口(噪音)。
    """
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(
        rows,
        domain=_orders_domain(),
        column_candidates={("shopee", "monthly"): SHOPEE_ORDER_COLUMNS},
    )

    commission_candidates = report.column_candidates.get(
        "shopee/monthly/platform_commission", ()
    )
    assert "联盟佣金(RMB)" not in commission_candidates
    assert "联盟佣金" not in commission_candidates
    # 「联盟佣金」与「联盟佣金(RMB)」归一化后同名 ⇒ 两者都被排除
    # (orders 域是封闭域: 裸名是原币列, 与 (RMB) 变体不可混谈)。
    fee_candidates = report.column_candidates["shopee/monthly/platform_service_fee"]
    assert "联盟佣金(RMB)" not in fee_candidates


def test_column_candidates_preserve_original_column_names():
    """候选必须保留原始列名 —— 归一化只用于比较, 不能改输出。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(
        rows,
        domain=_orders_domain(),
        column_candidates={("shopee", "monthly"): SHOPEE_ORDER_COLUMNS},
    )

    candidates = report.column_candidates["shopee/monthly/platform_service_fee"]
    # 原始列名必须保留(RMB 后缀不被吃掉)。
    assert "海外免退服务费(RMB)" in candidates


def test_registered_columns_are_not_proposed_as_unregistered_candidates():
    """字典里**已登记**的列名不该被当成「列名未登记」的候选。

    「Shopee平台佣金(RMB)」已登记给 platform_commission、「平台SKU」已登记给
    platform_sku ⇒ 它们不是「没登记的列名」。
    """
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(
        rows,
        domain=_orders_domain(),
        column_candidates={("shopee", "monthly"): SHOPEE_ORDER_COLUMNS},
    )

    candidates = report.column_candidates["shopee/monthly/platform_service_fee"]
    assert "Shopee平台佣金(RMB)" not in candidates
    assert "平台SKU" not in candidates
    assert "订单编号" not in candidates
    # 「服务费(RMB)」已登记给 platform_service_fee ⇒ 不是未登记候选。
    assert "服务费(RMB)" not in candidates


def test_column_candidate_ranking_is_deterministic():
    """同样的输入 ⇒ 同样的候选与顺序(相似度算法必须确定性)。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    def _candidates() -> tuple[str, ...]:
        report = build_coverage_report(
            rows,
            domain=_orders_domain(),
            column_candidates={("shopee", "monthly"): SHOPEE_ORDER_COLUMNS},
        )
        return report.column_candidates["shopee/monthly/platform_service_fee"]

    assert _candidates() == _candidates()


def test_column_candidate_limit_is_respected():
    """候选数量上限可配(默认 5 个)。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]
    many_columns = tuple(f"平台佣金备选{index}" for index in range(20))

    report = build_coverage_report(
        rows,
        domain=_orders_domain(),
        column_candidates={("shopee", "monthly"): many_columns},
        candidate_limit=3,
    )

    candidates = report.column_candidates["shopee/monthly/platform_commission"]
    assert len(candidates) == 3
    assert DEFAULT_CANDIDATE_LIMIT == 5


def test_zero_resolution_without_column_names_still_warns():
    """拿不到真实列名时, 告警照发 —— 只是没有候选那一段。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(rows, domain=_orders_domain())

    commission_warnings = [w for w in report.warnings if "platform_commission" in w]
    assert commission_warnings
    assert "解析率 0%" in commission_warnings[0]
    assert "疑似列名未登记" in commission_warnings[0]
    assert "源表实际列名候选：" not in commission_warnings[0]
    assert report.column_candidates == {}


def test_column_names_sql_reads_raw_data_keys_and_is_read_only():
    """真实列名的采集 SQL 必须走 raw_data 的 key, 且只读。"""
    sql = build_column_names_sql(_orders_domain())

    assert "jsonb_object_keys" in sql
    assert "semantic.fact_orders_atomic" in sql
    assert "column_names" in sql
    for keyword in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"):
        assert keyword not in sql.upper()


def test_column_names_sql_can_filter_groups():
    """可以只采指定 (平台, 粒度) 组 —— 避免无谓的全表扫描。"""
    sql = build_column_names_sql(
        _orders_domain(),
        groups=[("shopee", "monthly")],
    )

    assert "('shopee', 'monthly')" in sql
    assert "WHERE (s.platform_code, s.granularity) IN" in sql


# ── 6. 平台维度诊断（阶段 5.3） ─────────────────────────────────────


def test_platform_summary_lists_fields_that_never_resolve():
    """平台维度诊断: 汇总「所有粒度都解析不出来」的字段。"""
    rows = [
        _orders_row("shopee", "monthly", total_rows=100),
        _orders_row("shopee", "daily", total_rows=100),
        _orders_row("tiktok", "monthly", total_rows=100, resolved={"order_id": 100}),
    ]

    report = build_coverage_report(rows, domain=_orders_domain())

    summaries = {summary.platform_code: summary for summary in report.platforms}
    assert set(summaries) == {"shopee", "tiktok"}
    shopee = summaries["shopee"]
    # ⚠ 该平台**适用**的标准字段数(不是全集) —— 见下一条用例:
    #   有的字段只适用部分平台(如 total_income 只有 tiktok 有)。
    assert shopee.total_fields == len(platform_applicable_fields("orders", "shopee"))
    assert shopee.total_fields <= len(ORDERS_STANDARD_FIELDS)
    # shopee 两个粒度全 0% ⇒ 这些字段一次都没解析出来。
    assert "platform_commission" in shopee.zero_standard_fields
    assert shopee.zero_fields == len(shopee.zero_standard_fields)
    assert shopee.zero_rate > 0
    # tiktok 的 order_id 解析成功 ⇒ 不算「一次都没解析出来」。
    tiktok = summaries["tiktok"]
    assert "order_id" not in tiktok.zero_standard_fields


def test_platform_summary_produces_warning_without_field_names():
    """平台级告警存在, 但**不罗列字段名** —— 避免与字段级告警重复刷屏。"""
    rows = [_orders_row("shopee", "monthly", total_rows=100)]

    report = build_coverage_report(rows, domain=_orders_domain())

    platform_warnings = [w for w in report.warnings if "平台" in w]
    assert platform_warnings
    assert "shopee" in platform_warnings[0]
    assert "platform_commission" not in platform_warnings[0]


def test_healthy_platform_has_no_platform_warning():
    """所有字段都解析成功 ⇒ 没有平台级告警。"""
    rows = [
        _orders_row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved={field.standard_field: 100 for field in ORDERS_STANDARD_FIELDS},
        )
    ]

    report = build_coverage_report(rows, domain=_orders_domain())

    assert report.warnings == ()
    assert report.platforms[0].zero_fields == 0


def test_platform_summary_skips_fields_not_applicable_to_platform():
    """只在该平台有源列的字段, 不该让**别的**平台报缺(否则是噪音)。

    ``total_income``(卖家总收入)只有 tiktok 有这一列; shopee 侧的对应概念是
    「预估回款金额 / 已结算金额」—— 那是**结算口径**, 不是商品收入口径。
    ⇒ shopee 的平台诊断里**不该**出现 ``total_income``。

    ⚠ 反过来: 跨平台通用语义的字段(如 ``platform_service_fee``,
      tiktok 把费用拆成了多列)仍然照常报 —— 那是**真实缺口**, 不能被过滤掉。
    """
    rows = [
        _orders_row("shopee", "monthly", total_rows=100),
        _orders_row(
            "tiktok", "monthly", total_rows=100, resolved={"total_income": 100}
        ),
    ]

    report = build_coverage_report(rows, domain=_orders_domain())

    summaries = {summary.platform_code: summary for summary in report.platforms}
    shopee = summaries["shopee"]
    tiktok = summaries["tiktok"]

    # shopee 不适用 total_income ⇒ 不计入字段总数, 也不进 zero 列表。
    assert "total_income" not in shopee.zero_standard_fields
    assert shopee.total_fields == len(platform_applicable_fields("orders", "shopee"))
    # tiktok 适用 ⇒ 解析成功就不算缺。
    assert "total_income" not in tiktok.zero_standard_fields
    assert tiktok.total_fields == len(platform_applicable_fields("orders", "tiktok"))
    # 跨平台通用语义的字段仍然纳入诊断(tiktok 解析不出来 ⇒ 真实缺口)。
    assert "platform_service_fee" in tiktok.zero_standard_fields


def test_platform_applicable_fields_follows_dictionary_platforms_marker():
    """平台适用性是**字典里的一份事实**, 不是各处的硬编码。"""
    from backend.services.semantic_field_registry import (
        SEMANTIC_FIELD_DEFINITIONS,
        semantic_field_applies_to_platform,
    )

    meta = SEMANTIC_FIELD_DEFINITIONS["total_income"]
    assert tuple(meta["platforms"]) == ("tiktok",)
    assert semantic_field_applies_to_platform("total_income", "tiktok") is True
    assert semantic_field_applies_to_platform("total_income", "shopee") is False
    # 没标 platforms 的字段 ⇒ 跨平台通用。
    assert "platforms" not in SEMANTIC_FIELD_DEFINITIONS["platform_service_fee"]
    assert semantic_field_applies_to_platform("platform_service_fee", "tiktok") is True
    # 两平台都有的字段(联盟/达人佣金)⇒ 两平台都适用。
    assert semantic_field_applies_to_platform("affiliate_commission", "shopee") is True
    assert semantic_field_applies_to_platform("affiliate_commission", "tiktok") is True
