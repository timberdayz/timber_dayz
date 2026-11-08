"""tiktok 的「商品访客数」接通为 TikTok 侧 UV(``visitor_count``)的守护用例。

背景
----
2026-11-10 实测(开发库全仓扫描 ``raw_data`` 的 key):

* shopee 流量月报 2354 行 —— 访客列**只有**「访客数」「新访客」「现有访客」;
* tiktok 流量月报 1374 行 —— 访客列**只有**「商品访客数」
  (店铺级访客数这一列**压根不存在**);
* ⇒ 两边访客列名**互斥** ⇒ 「访客数」是 shopee 专有,「商品访客数」是 tiktok 专有。

⇒ tiktok 侧的 UV 就是「商品访客数」。这**不是新增口径**, 而是把 2026-05-26
的架构契约(``docs/architecture/SEMANTIC_FIELD_RULES.md``:「TikTok analytics
explicitly maps ``商品访客数`` to canonical ``visitor_count``」)落进实现。

⚠⚠ **两平台的 UV 不是同一个口径**:

* shopee「访客数」     = 全店**去重访客人数**(实测 519,212 人)
* tiktok「商品访客数」 = 按商品统计的**访客人次**(实测 175,914 人次)

⇒ 跨平台**不可直接比大小** ⇒ 看板必须标注(前端 ``businessOverviewKpiMeta.js``)。

本文件把最容易做错的四件事钉死:

1. 两个平台**必须对称登记** —— 只登记一边会把另一边**静默挤掉**;
2. 「商品访客数」在 analytics 域**只**归 ``visitor_count``;
3. ``product_visitor_count`` **退出** analytics 域, 但**留在** products 域;
4. 口径差异必须在看板上**显式标注**(不许悄悄比大小)。
"""

import re
from pathlib import Path

from backend.services.semantic_alias_registry import build_domain_alias_records
from backend.services.semantic_coverage_audit_service import ANALYTICS_STANDARD_FIELDS
from backend.services.semantic_field_registry import (
    ANALYTICS_PLATFORM_ALIASES,
    ANALYTICS_SEMANTIC_ALIASES,
    DOMAIN_PLATFORM_SEMANTIC_ALIASES,
    DOMAIN_SEMANTIC_ALIASES,
    PRODUCTS_SEMANTIC_ALIASES,
    SEMANTIC_FIELD_DEFINITIONS,
    platform_applicable_fields,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DAILY_VIEW_ASSET = REPO_ROOT / "sql" / "semantic" / "analytics_atomic.sql"
MONTHLY_MV_ASSET = REPO_ROOT / "sql" / "semantic" / "analytics_monthly_atomic_mv.sql"
MONTHLY_VIEW_ASSET = REPO_ROOT / "sql" / "semantic" / "analytics_monthly_atomic.sql"
ALIAS_ASSET = REPO_ROOT / "sql" / "semantic" / "semantic_alias_registry.sql"
MIGRATION_ASSET = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261211_semantic_analytics_tiktok_visitor_count.py"
)

#: 两条链的资产(必须**同口径**)。
CHAIN_ASSETS = (DAILY_VIEW_ASSET, MONTHLY_MV_ASSET)

#: 本次接通的访客列: 平台 -> 真实表头 -> 标准字段。
VISITOR_HEADERS = {
    "shopee": ("访客数", "visitor_count"),
    "tiktok": ("商品访客数", "visitor_count"),
}

#: 「商品访客数」在 analytics 域的**唯一**归属。
VISITOR_FIELD = "visitor_count"

#: 「商品访客数」在 analytics 域的**旧**归属(必须被清掉)。
LEGACY_VISITOR_FIELD = "product_visitor_count"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── 一、字典 ────────────────────────────────────────────────────────────


def test_visitor_count_is_defined_in_dictionary_as_analytics_metric():
    """``visitor_count`` 必须在字典里有定义, 且是 analytics 域的 metric。"""
    meta = SEMANTIC_FIELD_DEFINITIONS.get(VISITOR_FIELD)
    assert meta is not None, "标准字段 {0} 不在字典里".format(VISITOR_FIELD)
    assert meta.get("kind") == "metric"
    assert meta.get("domain") == "analytics"


def test_product_visitor_count_has_left_the_analytics_domain():
    """``product_visitor_count`` 必须**退出** analytics 域。

    为什么: analytics 域的「商品访客数」现在归 ``visitor_count``
    ⇒ 若本域再登记一条 ``product_visitor_count``, 同一个列名就会同时指向
    两个标准字段(SSOT 硬约束: 一个列名只认一个标准字段)。
    """
    meta = SEMANTIC_FIELD_DEFINITIONS.get(LEGACY_VISITOR_FIELD)
    assert meta is not None, "标准字段 {0} 不在字典里".format(LEGACY_VISITOR_FIELD)
    assert (
        meta.get("domain") == "products"
    ), "product_visitor_count 应属于 products 域, 实际 {0}".format(meta.get("domain"))
    assert (
        LEGACY_VISITOR_FIELD not in ANALYTICS_SEMANTIC_ALIASES
    ), "product_visitor_count 不该再出现在 analytics 域限定别名表里"
    assert LEGACY_VISITOR_FIELD not in DOMAIN_SEMANTIC_ALIASES.get("analytics", {})


def test_product_visitor_count_still_serves_the_products_domain():
    """``product_visitor_count`` 必须**留在** products 域(「商品访客数量」)。

    实测 products 域 25809 行有「商品访客数量」⇒ 撤掉它就是**丢了真实数据**。
    """
    assert "商品访客数量" in PRODUCTS_SEMANTIC_ALIASES.get(
        LEGACY_VISITOR_FIELD, ()
    ), "products 域的「商品访客数量」不能丢"
    products_records = build_domain_alias_records("products")
    assert any(
        row["standard_field"] == LEGACY_VISITOR_FIELD
        and row["raw_alias"] == "商品访客数量"
        for row in products_records
    ), "products 域必须还登记着 product_visitor_count <- 商品访客数量"


def test_product_visitor_count_global_aliases_drop_the_ambiguous_chinese_name():
    """``product_visitor_count`` 的**全局**别名不许再含中文「商品访客数」。

    全局别名会被套到**任何**用到该字段的域 ⇒ 留着中文裸名 = 任何域的同名列
    都会被它认领 ⇒ 一个列名指向两个标准字段。
    """
    for alias in SEMANTIC_FIELD_DEFINITIONS[LEGACY_VISITOR_FIELD].get("aliases") or ():
        assert not re.search(
            r"[一-鿿]", alias
        ), "product_visitor_count 的全局别名不许含中文裸名: {0!r}".format(alias)


# ── 二、别名登记 ────────────────────────────────────────────────────────


def test_visitor_headers_are_registered_as_platform_scoped_aliases():
    """两个平台的访客列必须登记在**平台限定**别名表里。"""
    assert "analytics" in DOMAIN_PLATFORM_SEMANTIC_ALIASES
    assert DOMAIN_PLATFORM_SEMANTIC_ALIASES["analytics"] is ANALYTICS_PLATFORM_ALIASES
    for platform, (header, field) in VISITOR_HEADERS.items():
        aliases = ANALYTICS_PLATFORM_ALIASES.get(platform) or {}
        assert header in (aliases.get(field) or ()), "{0} 的「{1}」没登记到 {2}".format(
            platform, header, field
        )


def test_visitor_headers_are_registered_on_both_platforms():
    """两个平台**必须都登记** —— 这条最容易做错。

    别名合并规则(:func:`build_domain_alias_records`)里有一条**排他**规则:
    某个标准字段一旦出现在 ``platform_fields``(即登记了平台限定别名), 它的
    **通用别名就整体不再登记** ⇒ 只登记一边会把另一边**一起挤掉**
    ⇒ 那一边会**静默**变 NULL(没有任何报错)。

    ⇒ 这条断言钉住「对称登记」这个前提。
    """
    for platform in VISITOR_HEADERS:
        assert (
            platform in ANALYTICS_PLATFORM_ALIASES
        ), "{0} 侧没有登记任何访客别名 —— 会被排他规则挤掉".format(platform)
        assert VISITOR_FIELD in (
            ANALYTICS_PLATFORM_ALIASES.get(platform) or {}
        ), "{0} 侧必须登记 {1}".format(platform, VISITOR_FIELD)


def test_visitor_headers_are_not_registered_as_generic_aliases():
    """两个平台的访客列**不许**出现在域限定(通用)别名表里。

    通用别名 = 两个平台都能命中 ⇒ 将来任一平台出现同名列时会**串口径**
    (这正是 2026-11-08 edb7921a 修掉的病根)。
    """
    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    for platform, (header, _field) in VISITOR_HEADERS.items():
        assert header not in generic, "{0} 不该进通用别名表(通用别名会串口径)".format(
            header
        )


def test_one_column_name_maps_to_exactly_one_standard_field_in_analytics():
    """SSOT 硬约束: analytics 域里一个列名只认一个标准字段。

    ⚠ 这里**跨域限定 + 平台限定**一起判重: 同一个列名挂在两个标准字段上时,
    ``semantic.resolve_alias()`` 会让两个字段**各自**取到值 ⇒ 下游会把同一个
    数字当成两个不同的业务事实。
    """
    owners = {}
    for field, aliases in ANALYTICS_SEMANTIC_ALIASES.items():
        for alias in aliases:
            previous = owners.setdefault(alias, field)
            assert previous == field, "列名 {0!r} 同时归 {1} 与 {2}".format(
                alias, previous, field
            )
    for platform, per_platform in ANALYTICS_PLATFORM_ALIASES.items():
        for field, aliases in per_platform.items():
            for alias in aliases:
                key = (platform, alias)
                previous = owners.setdefault(key, field)
                assert previous == field, "列名 {0!r}({1}) 同时归 {2} 与 {3}".format(
                    alias, platform, previous, field
                )


def test_product_visitors_resolve_to_visitor_count_not_product_visitor_count():
    """「商品访客数」在 analytics 域**只**归 ``visitor_count``。"""
    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    assert "商品访客数" not in generic, "「商品访客数」不许留在通用别名表里"

    analytics_records = build_domain_alias_records("analytics")
    owners = set()
    for row in analytics_records:
        if row["raw_alias"] == "商品访客数":
            owners.add(row["standard_field"])
    assert owners == {VISITOR_FIELD}, "「商品访客数」应只归 {0}, 实际 {1}".format(
        VISITOR_FIELD, sorted(owners)
    )


def test_analytics_records_carry_both_platform_visitor_rows():
    """派生出来的别名行里, 两个平台的访客行都在, 且平台维度正确。"""
    records = build_domain_alias_records("analytics")
    visitor_rows = {
        (str(row["platform_code"] or ""), str(row["raw_alias"]))
        for row in records
        if row["standard_field"] == VISITOR_FIELD
    }
    for platform, (header, _field) in VISITOR_HEADERS.items():
        assert (
            platform,
            header,
        ) in visitor_rows, "analytics 域缺 {0}/{1} 的访客别名行".format(
            platform, header
        )


def test_platform_applicable_fields_include_visitor_count_for_both_platforms():
    """平台诊断: ``visitor_count`` 对两个平台都要纳入。"""
    for platform in VISITOR_HEADERS:
        applicable = platform_applicable_fields("analytics", platform)
        assert VISITOR_FIELD in applicable, "{0} 侧漏了 {1}".format(
            platform, VISITOR_FIELD
        )


def test_analytics_coverage_audits_visitor_count_but_not_product_visitor_count():
    """巡检字段集: 有 ``visitor_count``, 没有 ``product_visitor_count``。

    为什么: ``product_visitor_count`` 在 analytics 域**没有源列**了 ⇒ 留在
    巡检集合里只会报「源表没有这一列」的假缺口 ⇒ 噪音掩盖真问题。
    """
    audited = {field.standard_field for field in ANALYTICS_STANDARD_FIELDS}
    assert VISITOR_FIELD in audited, "流量域巡检漏了 {0}".format(VISITOR_FIELD)
    assert (
        LEGACY_VISITOR_FIELD not in audited
    ), "product_visitor_count 已退出 analytics 域, 不该再被巡检"


# ── 三、两条链的取数 ────────────────────────────────────────────────────


def test_both_chains_resolve_visitor_count_through_alias_registry():
    """两条链都必须走 ``semantic.resolve_alias()`` 取 visitor_count。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        assert "semantic.resolve_alias(" in sql_text
        assert "'{0}'".format(VISITOR_FIELD) in sql_text


def test_both_chains_do_not_inline_visitor_headers():
    """不许内联手写表头取数(那会让别名表形同虚设)。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for _platform, (header, _field) in VISITOR_HEADERS.items():
            assert (
                "raw_data->>'{0}'".format(header) not in sql_text
            ), "{0} 仍在内联取 {1}".format(asset.name, header)


def test_visitor_count_column_position_is_unchanged():
    """``visitor_count`` 列的**位置**不许变(下游 mart 按列名取数)。"""
    sql_text = _read(DAILY_VIEW_ASSET)
    tail = sql_text.rsplit("FROM deduplicated", 1)[0]
    positions = []
    for column in ("visitor_count", "page_views", "impressions"):
        marker = "{0} AS {0}".format(column)
        index = tail.rfind(marker)
        assert index > 0, "输出层缺列 {0}".format(column)
        positions.append(index)
    assert positions == sorted(positions), "visitor_count 列的相对顺序变了"


def test_monthly_view_still_exposes_visitor_and_product_visitor_columns():
    """月度普通视图仍要输出这两列(列集是既有契约, 不许因为本次改造而少列)。"""
    sql_text = _read(MONTHLY_VIEW_ASSET)
    for field in (VISITOR_FIELD, LEGACY_VISITOR_FIELD):
        assert field in sql_text, "月度视图缺列 {0}".format(field)


def test_no_fake_zero_coalesce_in_either_chain():
    """两条链都不许用 ``COALESCE(x, 0)`` 伪装「不知道」。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        assert not re.search(r"COALESCE\(\s*\w+\s*,\s*0\s*\)\s+AS", sql_text)


# ── 四、别名资产与迁移 ──────────────────────────────────────────────────


def test_alias_seed_contains_platform_scoped_visitor_rows():
    """别名资产里必须有这两条 ``analytics`` 的**平台限定** builtin 行。"""
    alias_text = _read(ALIAS_ASSET)
    for platform, (header, field) in VISITOR_HEADERS.items():
        needle = "('analytics', '{field}', '{header}', '{platform}'".format(
            field=field, header=header, platform=platform
        )
        assert needle in alias_text, "别名资产缺 {0} 的平台限定行".format(platform)


def test_alias_seed_has_no_generic_visitor_rows():
    """别名资产里**不许**再有通用的访客行(会串口径)。"""
    alias_text = _read(ALIAS_ASSET)
    for _platform, (header, _field) in VISITOR_HEADERS.items():
        needle = "('analytics', 'visitor_count', '{header}', NULL".format(header=header)
        assert needle not in alias_text, "别名资产仍有通用访客行: {0}".format(needle)
    legacy_needle = "('analytics', 'product_visitor_count', '商品访客数', NULL"
    assert (
        legacy_needle not in alias_text
    ), "别名资产仍有 product_visitor_count 的通用行"


def test_migration_file_exists_and_chains_from_previous_revision():
    """迁移文件存在, 且挂在 20261210 之后。"""
    assert MIGRATION_ASSET.is_file(), "缺迁移文件 {0}".format(MIGRATION_ASSET.name)
    migration_text = _read(MIGRATION_ASSET)
    assert (
        'revision = "current_schema_20261211_semantic_analytics_tiktok_visitor"'
        in migration_text
    )
    assert (
        'down_revision = "current_schema_20261210_semantic_analytics_tiktok_attribution"'
        in migration_text
    )


def test_migration_has_fail_closed_self_checks():
    """迁移必须有 fail-closed 自检。

    ⚠ 少一条自检 = 迁移「看起来成功」但线上取数是错的 ⇒ 必须钉死。
    """
    migration_text = _read(MIGRATION_ASSET)
    assert "_assert_no_ambiguous_aliases" in migration_text
    assert "_assert_visitor_count_aliases" in migration_text
    assert "_assert_visitor_count_resolution" in migration_text
    assert "_assert_visitor_count_values" in migration_text


def test_migration_migrates_confirmed_alias_rows_and_template_bindings():
    """迁移必须**显式**处理「用户确认过的行」(seed 的清理段只删 builtin)。"""
    migration_text = _read(MIGRATION_ASSET)
    assert "_migrate_confirmed_alias_rows" in migration_text
    assert "_migrate_template_bindings" in migration_text
    assert "core.field_mapping_templates" in migration_text


def test_migration_refreshes_both_chains():
    """两条链必须一起刷新(同源同口径 ⇒ 同一个指标在两条链上取到同一个值)。"""
    migration_text = _read(MIGRATION_ASSET)
    assert "REFRESH MATERIALIZED VIEW" in migration_text
    assert "semantic.fact_analytics_atomic_mv" in migration_text
    assert "semantic.fact_analytics_monthly_atomic_mv" in migration_text
