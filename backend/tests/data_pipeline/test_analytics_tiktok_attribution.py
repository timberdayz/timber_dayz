"""tiktok 的 13 个 GMV 归因列接进语义层的守护用例。

背景
----
2026-11-09 实测(开发库 ``b_class.fact_tiktok_analytics_monthly`` 1374 行):
tiktok 流量报表里有 13 个 GMV 归因列, 之前**既没有标准字段、也没进语义层**:

    商品卡 GMV / 商家直播 GMV / 商家直播间接 GMV / 商家视频 GMV /
    商家视频间接 GMV / 绑定账号直播归因 GMV / 绑定账号视频归因 GMV /
    联盟视频归因 GMV / 达人直播 GMV / 达人直播归因 GMV /
    达人直播间接 GMV / 达人视频 GMV / 达人视频间接 GMV

⚠⚠ **最关键的一条: 这批列绝不能相加** ——
    13 列合计 1,072,030.01 vs 总成交额 1,092,456.33(占 98.13%);
    **逐行**看: 741 个可比行里 **376 行(50.7%)归因和 > 该行总额**
    (比值中位 1.019、最大 2.000)
    ⇒ 同一笔成交被多个维度**重复记账**(在直播间看到 → 点商品卡下单 →
      分享出去 ⇒ 平台把这单记到达人直播、商品卡等多个口径上)。
    ⇒ 用户 2026-11-09 决定: **一列一个标准字段, 只单列展示, 绝不聚合**。

本文件把这批列的口径钉死 —— 尤其钉死「不许聚合」和「平台限定」。
"""

from pathlib import Path

from backend.services.semantic_field_registry import (
    ANALYTICS_PLATFORM_ALIASES,
    ANALYTICS_SEMANTIC_ALIASES,
    DOMAIN_PLATFORM_SEMANTIC_ALIASES,
    SEMANTIC_FIELD_DEFINITIONS,
    SEMANTIC_FIELD_DESCRIPTIONS,
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
    / "20261210_semantic_analytics_tiktok_attribution.py"
)

#: 源表 13 个 GMV 归因列 -> 标准字段。
ATTRIBUTION_FIELDS = {
    "商品卡 GMV": "product_card_gmv",
    "商家直播 GMV": "live_gmv",
    "商家直播间接 GMV": "live_indirect_gmv",
    "商家视频 GMV": "video_gmv",
    "商家视频间接 GMV": "video_indirect_gmv",
    "绑定账号直播归因 GMV": "bound_account_live_attributed_gmv",
    "绑定账号视频归因 GMV": "bound_account_video_attributed_gmv",
    "联盟视频归因 GMV": "affiliate_video_attributed_gmv",
    "达人直播 GMV": "creator_live_gmv",
    "达人直播归因 GMV": "creator_live_attributed_gmv",
    "达人直播间接 GMV": "creator_live_indirect_gmv",
    "达人视频 GMV": "creator_video_gmv",
    "达人视频间接 GMV": "creator_video_indirect_gmv",
}

#: 两条链的资产(必须**同口径**)。
CHAIN_ASSETS = (DAILY_VIEW_ASSET, MONTHLY_MV_ASSET)

#: 实测恒为 0 的列(有列、无值)—— 说明文字里必须点出来。
ALWAYS_ZERO_FIELDS = (
    "live_gmv",
    "live_indirect_gmv",
    "bound_account_live_attributed_gmv",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── 一、字典 ────────────────────────────────────────────────────────────


def test_attribution_fields_are_defined_in_dictionary():
    """13 个归因列都要有标准字段, 且是 analytics 域的 metric。"""
    for header, field in ATTRIBUTION_FIELDS.items():
        meta = SEMANTIC_FIELD_DEFINITIONS.get(field)
        assert meta is not None, "{0} 没有标准字段".format(header)
        assert meta.get("kind") == "metric", "{0} 不是 metric".format(field)
        assert meta.get("domain") in (
            "analytics",
            "attribution",
        ), "{0} 的域不对: {1}".format(field, meta.get("domain"))


def test_attribution_fields_are_marked_tiktok_only():
    """这 13 列**只有 tiktok 有** ⇒ 必须标 ``platforms=("tiktok",)``。

    实测: shopee 的流量报表(2354 行)里这 13 列**一个都没有**。
    不标 ⇒ 巡检会对 shopee 报「缺这 13 个指标」= 噪音。
    """
    for header, field in ATTRIBUTION_FIELDS.items():
        meta = SEMANTIC_FIELD_DEFINITIONS[field]
        platforms = tuple(meta.get("platforms") or ())
        assert platforms == (
            "tiktok",
        ), "{0}({1}) 的 platforms 应为 tiktok, 实际 {2}".format(
            header, field, platforms
        )


def test_reused_fields_keep_their_original_aliases():
    """4 个被**复用**的字段, 别名必须仍与源表列名逐字一致。

    复用而不是另造字段 ⇒ SSOT: 一个业务事实只允许一个标准字段。
    """
    for header, field in (
        ("商家直播 GMV", "live_gmv"),
        ("商家直播间接 GMV", "live_indirect_gmv"),
        ("商家视频 GMV", "video_gmv"),
        ("商家视频间接 GMV", "video_indirect_gmv"),
    ):
        aliases = SEMANTIC_FIELD_DEFINITIONS[field].get("aliases") or ()
        assert header in aliases, "{0} 的别名里丢了 {1!r}".format(field, header)


def test_speculative_attribution_aliases_are_not_registered():
    """源表**没有**的推测性别名不许登记进别名表。

    「商家直播归因 GMV」「商家视频归因 GMV」在源表里不存在
    (实测 1374 行的 raw_data key 里没有)⇒ 登记了也永远命不中。
    ⇒ 它们对应的字段本轮**不登记** ⇒ 巡检不会报「解析率 0%」的假缺口。
    """
    registered = set()
    for per_platform in ANALYTICS_PLATFORM_ALIASES.values():
        for aliases in per_platform.values():
            registered.update(aliases)
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        registered.update(aliases)

    for absent in ("商家直播归因 GMV", "商家视频归因 GMV"):
        assert absent not in registered, "{0!r} 在源表里不存在, 不该登记".format(absent)


def test_always_zero_columns_are_documented_as_zero():
    """实测恒为 0 的列, 说明文字里必须点出来。

    「有列、值恒 0」分不清「该渠道真的没成交」与「平台没回传」⇒
    必须在文案里如实标注, 不能让读数的人误以为这是结论。
    """
    for field in ALWAYS_ZERO_FIELDS:
        description = SEMANTIC_FIELD_DESCRIPTIONS.get(field, "")
        assert "恒为 0" in description, "{0} 的说明没标注「恒为 0」".format(field)


# ── 二、别名登记 ────────────────────────────────────────────────────────


def test_attribution_headers_are_registered_as_tiktok_platform_aliases():
    """13 个真实表头必须登记在 **tiktok 平台限定**别名表里。"""
    assert "analytics" in DOMAIN_PLATFORM_SEMANTIC_ALIASES
    tiktok_aliases = ANALYTICS_PLATFORM_ALIASES.get("tiktok") or {}
    for header, field in ATTRIBUTION_FIELDS.items():
        aliases = tiktok_aliases.get(field) or ()
        assert header in aliases, "{0} 没登记真实表头 {1!r}".format(field, header)


def test_attribution_headers_are_not_generic_aliases():
    """这 13 个表头**不许**出现在通用(域限定)别名表里。

    通用别名 = 两个平台都能命中 ⇒ 将来别的平台出现同名列时**串口径**。
    """
    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    for header in ATTRIBUTION_FIELDS:
        assert header not in generic, "{0!r} 不该进通用别名表".format(header)


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


def test_platform_applicable_fields_include_attribution_for_tiktok_only():
    """平台诊断: tiktok 要纳入这 13 个字段, shopee **不许**纳入。"""
    shopee_fields = platform_applicable_fields("analytics", "shopee")
    tiktok_fields = platform_applicable_fields("analytics", "tiktok")
    for field in ATTRIBUTION_FIELDS.values():
        assert field in tiktok_fields, "tiktok 侧漏了 {0}".format(field)
        assert field not in shopee_fields, "shopee 侧不该有 {0}(平台没这列)".format(
            field
        )


# ── 三、两条链: 取数、输出、以及「不许聚合」 ────────────────────────────


def test_both_chains_resolve_attribution_fields_through_alias_registry():
    """两条链都必须走 ``semantic.resolve_alias()`` 取这 13 个字段。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for field in ATTRIBUTION_FIELDS.values():
            assert (
                "'{field}'".format(field=field) in sql_text
            ), "{0} 没在 {1} 里取数".format(field, asset.name)


def test_both_chains_do_not_inline_attribution_headers():
    """不许内联手写表头取数(别名表是唯一事实源)。"""
    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        for header in ATTRIBUTION_FIELDS:
            assert (
                "raw_data->>'{0}'".format(header) not in sql_text
            ), "{0} 仍在内联取 {1}".format(asset.name, header)


def test_both_chains_output_attribution_columns():
    """两条链(以及月度普通视图)都必须输出这 13 列。"""
    for asset in CHAIN_ASSETS + (MONTHLY_VIEW_ASSET,):
        sql_text = _read(asset)
        for field in ATTRIBUTION_FIELDS.values():
            assert field in sql_text, "{0} 缺列 {1}".format(asset.name, field)


def _final_select_columns(text: str, marker: str) -> list:
    """取最终 SELECT 的输出列名(按出现顺序)。

    ⚠ 不能用 ``rfind(field)`` 定位 —— ``video_gmv`` 是 ``creator_video_gmv``
    的**子串** ⇒ 会命中错的位置。
    """
    block = text.rsplit(marker, 1)[0]
    block = block.rsplit("SELECT", 1)[1]
    columns = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        line = line.rstrip(",")
        if " AS " in line:
            line = line.rsplit(" AS ", 1)[1]
        columns.append(line.strip())
    return columns


def test_attribution_columns_are_appended_at_the_end():
    """新列只能**追加** —— 既有列名列序一个都不能动。

    ⚠ 资产层(本用例)与迁移层(``_check_column_block``)口径**不同**, 且各有道理:
      * 资产是**当前快照** ⇒ 新列必须就在**最后**, 后面不许再有别的列
        ⇒ 这里保留**绝对末尾**断言(更强: 能发现「既有列被挪到新列后面」);
      * 迁移自检跑在**链上的历史点** ⇒ 那时后面可能已经有后续迁移的列
        ⇒ 那里只能断言「齐全 + 顺序 + 连续 + 追加在锚点之后」
        (2026-11-09 实际踩过: 绝对末尾断言会打断空库迁移链)。
    """
    expected_tail = [
        "new_visitor_count",
        "returning_visitor_count",
        "new_follower_count",
        "avg_session_duration_seconds",
        "avg_page_views_per_visitor",
    ] + list(ATTRIBUTION_FIELDS.values())

    daily_columns = _final_select_columns(_read(DAILY_VIEW_ASSET), "FROM deduplicated")
    monthly_columns = _final_select_columns(
        _read(MONTHLY_MV_ASSET), "FROM deduplicated_monthly_traffic"
    )
    for columns in (daily_columns, monthly_columns):
        # 1) 绝对末尾: 新列就在最后, 后面不许再有别的列。
        assert (
            columns[-len(expected_tail) :] == expected_tail
        ), "末尾 {0} 列不对: {1}".format(
            len(expected_tail), columns[-len(expected_tail) :]
        )
        # 2) 全部存在, 且相对顺序与登记顺序一致。
        for field in expected_tail:
            assert field in columns, "输出层缺列 {0}".format(field)
        positions = [columns.index(field) for field in expected_tail]
        assert positions == sorted(positions), "新登记列的相对顺序变了"
        # 3) 连续成块(中间插别的列 = 破坏列序契约)。
        assert (
            max(positions) - min(positions) == len(positions) - 1
        ), "新登记列必须连续成块, 实际下标 {0}".format(positions)
        # 4) 追加在锚点列之后(既有列一个都不许被挪到新列后面)。
        assert "identity_candidates" in columns, "输出层缺锚点列 identity_candidates"
        assert min(positions) > columns.index(
            "identity_candidates"
        ), "新登记列必须追加在 identity_candidates 之后"
        # 既有列名列序一个都不能动: 新列之前的部分必须仍是原样。
        assert "identity_candidates" in columns
        assert columns.index("identity_candidates") < columns.index("new_visitor_count")


def test_attribution_columns_are_never_aggregated():
    """⚠⚠ **这批列绝不能被求和** —— 钉死。

    实测 50.7% 的行归因和超过该行总额 ⇒ 相加出来的数是错的。
    ⇒ 视图里不许出现对这 13 列的 SUM / 跨列求和。
    """
    for asset in CHAIN_ASSETS + (MONTHLY_VIEW_ASSET,):
        sql_text = _read(asset).lower()
        for field in ATTRIBUTION_FIELDS.values():
            assert (
                "sum({0})".format(field) not in sql_text
            ), "{0} 对归因列 {1} 求了和".format(asset.name, field)
            assert (
                "sum({0} ".format(field) not in sql_text
            ), "{0} 对归因列 {1} 求了和".format(asset.name, field)


def test_no_fake_zero_coalesce_in_either_chain():
    """两条链都不许用 ``COALESCE(x, 0)`` 伪装「不知道」。

    shopee 没有这 13 列 ⇒ 填 0 等于宣称「shopee 的联盟 GMV 是 0」= **假的**。
    """
    import re

    for asset in CHAIN_ASSETS:
        sql_text = _read(asset)
        assert not re.search(r"COALESCE\(\s*\w+\s*,\s*0\s*\)\s+AS", sql_text)


# ── 四、别名资产与迁移 ──────────────────────────────────────────────────


def test_alias_seed_contains_tiktok_attribution_rows():
    """别名资产里必须有这 13 条 ``analytics``/``tiktok`` 的 builtin 行。"""
    alias_text = _read(ALIAS_ASSET)
    for header, field in ATTRIBUTION_FIELDS.items():
        needle = "('analytics', '{field}', '{header}', 'tiktok'".format(
            field=field, header=header
        )
        assert needle in alias_text, "别名资产缺 {0} 的平台限定行".format(field)


def test_migration_file_exists_and_chains_from_previous_revision():
    """迁移文件存在, 且挂在 20261209 之后。"""
    assert MIGRATION_ASSET.is_file(), "缺迁移文件 {0}".format(MIGRATION_ASSET.name)
    migration_text = _read(MIGRATION_ASSET)
    assert (
        'revision = "current_schema_20261210_semantic_analytics_tiktok_attribution"'
        in migration_text
    )
    assert (
        'down_revision = "current_schema_20261209_semantic_analytics_shopee_traffic"'
        in migration_text
    )


def test_migration_has_fail_closed_self_checks_including_no_aggregation():
    """迁移必须有 fail-closed 自检, **含「不许聚合」那一条**。"""
    migration_text = _read(MIGRATION_ASSET)
    assert "_assert_no_ambiguous_aliases" in migration_text
    assert "_assert_tiktok_attribution_aliases" in migration_text
    assert "_assert_traffic_columns" in migration_text
    assert "_assert_no_attribution_aggregation" in migration_text
