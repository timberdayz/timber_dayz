"""shopee 独有的 5 个流量指标接进语义层的守护用例。

背景
----
2026-11-09 实测(开发库 ``b_class.fact_shopee_analytics_monthly`` 2354 行):

* shopee 流量报表有 5 列之前**既没有标准字段、也没进语义层**:
  「新访客」「现有访客」「新关注者」「平均停留时长」「平均页面访问数」;
* 这 5 列 **2354/2354 行全部有值**, 按既有清洗链**全部可解析**;
* 「访客数」==「新访客」+「现有访客」—— **2354/2354 行精确相等**;
* 「新关注者」≤「访客数」—— **0 行违反**;
* 「平均页面访问数」≈「页面浏览数」÷「访客数」—— 1814 行可用行里
  **全部**在 ±0.02 内;
* 「平均停留时长」是 **HH:MM:SS 字符串**(形如 ``00:00:42``)
  ⇒ **不能**套普通数值清洗(``01:30:00`` 会被当成 ``13000``);
* tiktok 侧**没有**这 5 列(实测 1374 行 raw_data key 里一个都没有)
  ⇒ 必须走**平台限定**别名。

本文件把这些口径钉死 —— 尤其钉死三件容易做错的事:
1. 别名必须**平台限定**(tiktok 不能被误命中);
2. 「平均停留时长」必须**专门换算成秒**(不能套普通数值清洗);
3. 两条链(日/周 + 月度)**同源同口径**、新列只能**追加在末尾**。
"""

import re
from pathlib import Path

from backend.services.semantic_field_registry import (
    ANALYTICS_PLATFORM_ALIASES,
    ANALYTICS_SEMANTIC_ALIASES,
    DOMAIN_PLATFORM_SEMANTIC_ALIASES,
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
    / "20261209_semantic_analytics_shopee_traffic_fields.py"
)

#: 本次补登的 5 个标准字段 -> 平台限定别名(真实表头, 逐字)。
SHOPEE_TRAFFIC_FIELDS = {
    "new_visitor_count": "新访客",
    "returning_visitor_count": "现有访客",
    "new_follower_count": "新关注者",
    "avg_session_duration_seconds": "平均停留时长",
    "avg_page_views_per_visitor": "平均页面访问数",
}

#: 两条链的资产(必须**同口径**)。
CHAIN_ASSETS = (DAILY_VIEW_ASSET, MONTHLY_MV_ASSET)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── 一、字典 ────────────────────────────────────────────────────────────


def test_shopee_traffic_fields_are_defined_in_dictionary():
    """5 个标准字段必须在字典里有定义, 且是 analytics 域的 metric。"""
    for field in SHOPEE_TRAFFIC_FIELDS:
        meta = SEMANTIC_FIELD_DEFINITIONS.get(field)
        assert meta is not None, "标准字段 {0} 不在字典里".format(field)
        assert meta.get("kind") == "metric", "{0} 不是 metric".format(field)
        assert meta.get("domain") == "analytics", "{0} 不属于 analytics 域".format(
            field
        )


def test_shopee_traffic_fields_are_marked_shopee_only():
    """这 5 个指标**只有 shopee 有** ⇒ 必须标 ``platforms=("shopee",)``。

    不标 ⇒ 巡检会对 tiktok 报「缺这 5 个指标」= 噪音(平台上压根没有)。
    """
    for field in SHOPEE_TRAFFIC_FIELDS:
        meta = SEMANTIC_FIELD_DEFINITIONS[field]
        platforms = tuple(meta.get("platforms") or ())
        assert platforms == (
            "shopee",
        ), "{0} 的 platforms 应为 shopee, 实际 {1}".format(field, platforms)


def test_shopee_traffic_dictionary_aliases_are_english_only():
    """字典的 ``aliases`` **不许**放中文裸名。

    中文裸名(「新访客」…)是**平台限定**的表头 ⇒ 放进全局别名表 = 任何域的
    同名列都会被认领(SSOT 的「一个列名只认一个标准字段」)。
    """
    for field in SHOPEE_TRAFFIC_FIELDS:
        for alias in SEMANTIC_FIELD_DEFINITIONS[field].get("aliases") or ():
            assert not re.search(
                r"[一-鿿]", alias
            ), "{0} 的别名 {1!r} 含中文裸名".format(field, alias)


# ── 二、别名登记 ────────────────────────────────────────────────────────


def test_shopee_traffic_headers_are_registered_as_platform_scoped_aliases():
    """5 个真实表头必须登记在**平台限定**别名表里(platform_code=shopee)。"""
    assert "analytics" in DOMAIN_PLATFORM_SEMANTIC_ALIASES
    assert DOMAIN_PLATFORM_SEMANTIC_ALIASES["analytics"] is ANALYTICS_PLATFORM_ALIASES
    shopee_aliases = ANALYTICS_PLATFORM_ALIASES.get("shopee") or {}
    for field, header in SHOPEE_TRAFFIC_FIELDS.items():
        aliases = shopee_aliases.get(field) or ()
        assert header in aliases, "{0} 没登记真实表头 {1!r}".format(field, header)


def test_shopee_traffic_headers_are_not_registered_as_generic_aliases():
    """这 5 个表头**不许**出现在域限定(通用)别名表里。

    通用别名 = 两个平台都能命中 ⇒ 将来 tiktok 上线同名列时会**串口径**。
    """
    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    for field, header in SHOPEE_TRAFFIC_FIELDS.items():
        assert header not in generic, "{0} 不该进通用别名表".format(field)


def test_one_column_name_maps_to_exactly_one_standard_field_across_scopes():
    """SSOT 硬约束: 一个列名只认一个标准字段(**跨域限定 + 平台限定**)。"""
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


def test_platform_applicable_fields_include_new_fields_for_shopee_only():
    """平台诊断: shopee 要纳入这 5 个字段, tiktok **不许**纳入。"""
    shopee_fields = platform_applicable_fields("analytics", "shopee")
    tiktok_fields = platform_applicable_fields("analytics", "tiktok")
    for field in SHOPEE_TRAFFIC_FIELDS:
        assert field in shopee_fields, "shopee 侧漏了 {0}".format(field)
        assert field not in tiktok_fields, "tiktok 侧不该有 {0}(平台没有这列)".format(
            field
        )


# ── 三、两条链的取数与输出 ──────────────────────────────────────────────


def test_both_chains_resolve_shopee_traffic_fields_through_alias_registry():
    """两条链都必须走 ``semantic.resolve_alias()`` 取这 5 个字段。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for field in SHOPEE_TRAFFIC_FIELDS:
            assert (
                "'{field}'".format(field=field) in sql_text
            ), "{0} 没在 {1} 里取数".format(field, asset.name)


def test_both_chains_do_not_inline_shopee_traffic_headers():
    """不许内联手写表头取数(那会让别名表形同虚设)。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for header in SHOPEE_TRAFFIC_FIELDS.values():
            assert (
                "raw_data->>'{0}'".format(header) not in sql_text
            ), "{0} 仍在内联取 {1}".format(asset.name, header)


def test_both_chains_output_shopee_traffic_columns():
    """两条链都必须输出这 5 列。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for field in SHOPEE_TRAFFIC_FIELDS:
            assert field in sql_text, "{0} 缺列 {1}".format(asset.name, field)


def test_shopee_traffic_columns_are_appended_at_the_end():
    """新列只能**追加在末尾** —— 既有列名列序一个都不能动。

    ``CREATE OR REPLACE VIEW`` 不能改列序 ⇒ 新列插在中间会让物化视图的
    列集/列序与既有下游不一致。
    """
    daily_tail = _read(DAILY_VIEW_ASSET).rsplit("FROM deduplicated", 1)[0]
    monthly_tail = _read(MONTHLY_MV_ASSET).rsplit(
        "FROM deduplicated_monthly_traffic", 1
    )[0]
    for tail in (daily_tail, monthly_tail):
        positions = []
        for field in SHOPEE_TRAFFIC_FIELDS:
            index = tail.rfind(field)
            assert index > 0, "输出层缺列 {0}".format(field)
            positions.append(index)
        assert positions == sorted(positions), "新列的相对顺序变了"
        # 新列必须在 identity_candidates 之后(即真正的末尾)。
        assert min(positions) > tail.rfind(
            "identity_candidates"
        ), "新列必须追加在 identity_candidates 之后"


def test_avg_session_duration_is_converted_from_hms_not_numeric_regex():
    """「平均停留时长」必须**专门**按 HH:MM:SS 换算成秒。

    套普通数值清洗 ⇒ ``01:30:00`` 会被当成 ``13000``(小时被当成数字)。
    ⇒ 断言: SQL 里必须有 ``split_part`` 分段换算, 且该字段**没有**落到
    通用数值正则那套模板上。
    """
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        assert "split_part" in sql_text, "{0} 没有 HH:MM:SS 分段换算".format(asset.name)
        # 换算表达式必须把三段都乘上对应权重。
        assert "* 3600" in sql_text, "{0} 的秒数换算缺少小时权重".format(asset.name)
        assert "* 60" in sql_text, "{0} 的秒数换算缺少分钟权重".format(asset.name)
        # 时间格式必须被严格校验(小时 00~23 / 分秒 00~59)。
        assert "[0-5][0-9]" in sql_text, "{0} 没有校验分秒取值范围".format(asset.name)


def test_monthly_view_exposes_shopee_traffic_columns():
    """月度普通视图也要输出这 5 列(它是月度链的下游出口)。"""
    sql_text = _read(MONTHLY_VIEW_ASSET)
    for field in SHOPEE_TRAFFIC_FIELDS:
        assert field in sql_text, "月度视图缺列 {0}".format(field)


def test_no_fake_zero_coalesce_in_either_chain():
    """两条链都不许用 ``COALESCE(x, 0)`` 伪装「不知道」。

    tiktok 没有这 5 列 ⇒ 填 0 等于宣称「tiktok 的新访客是 0 人」= **假的**。
    """
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        assert not re.search(r"COALESCE\(\s*\w+\s*,\s*0\s*\)\s+AS", sql_text)


# ── 四、别名资产与迁移 ──────────────────────────────────────────────────


def test_alias_seed_contains_platform_scoped_shopee_traffic_rows():
    """别名资产里必须有这 5 条 ``analytics``/``shopee`` 的 builtin 行。"""
    alias_text = _read(ALIAS_ASSET)
    for field, header in SHOPEE_TRAFFIC_FIELDS.items():
        needle = "('analytics', '{field}', '{header}', 'shopee'".format(
            field=field, header=header
        )
        assert needle in alias_text, "别名资产缺 {0} 的平台限定行".format(field)


def test_migration_file_exists_and_chains_from_previous_revision():
    """迁移文件存在, 且挂在 20261208 之后。"""
    assert MIGRATION_ASSET.is_file(), "缺迁移文件 {0}".format(MIGRATION_ASSET.name)
    migration_text = _read(MIGRATION_ASSET)
    assert (
        'revision = "current_schema_20261209_semantic_analytics_shopee_traffic"'
        in migration_text
    )
    assert (
        'down_revision = "current_schema_20261208_semantic_analytics_alias_resolve"'
        in migration_text
    )


def test_migration_has_fail_closed_self_checks():
    """迁移必须有 fail-closed 自检(别名行在库 + 视图输出新列)。"""
    migration_text = _read(MIGRATION_ASSET)
    assert "_assert_no_ambiguous_aliases" in migration_text
    assert "_assert_shopee_traffic_aliases" in migration_text
    assert "_assert_traffic_columns" in migration_text
