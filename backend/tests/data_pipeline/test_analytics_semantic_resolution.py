"""analytics(流量)域「取数走别名表 + 不伪装成 0」的守护用例。

背景
----
2026-11-08 之前, ``semantic.fact_analytics_atomic`` 的取数是 12 段手写
``COALESCE(raw_data->>'...')`` 链, 与真实表头对不上的地方全靠「找不到就填 0」
掩盖; 输出层再套一层 ``COALESCE(x, 0)`` ⇒ **「不知道」被伪装成「0」**。

实测(开发库, 改造前): shopee 2355 行 / tiktok 1446 行的 ``impressions``、
``clicks``、``gmv``、``order_count`` 合计**全是 0** —— 绝大多数是**取不到值**。

本文件把这些口径钉死。
"""

import re
from pathlib import Path

from backend.services.semantic_field_registry import (
    ANALYTICS_PLATFORM_ALIASES,
    ANALYTICS_SEMANTIC_ALIASES,
    DOMAIN_SEMANTIC_ALIASES,
)
from backend.services.semantic_field_registry import (
    SEMANTIC_FIELD_DEFINITIONS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VIEW_ASSET = REPO_ROOT / "sql" / "semantic" / "analytics_atomic.sql"
ALIAS_ASSET = REPO_ROOT / "sql" / "semantic" / "semantic_alias_registry.sql"


#: 实测真实表头(开发库 2026-11-08, ``b_class.fact_*_analytics_*`` 的 raw_data key)。
#:
#: ⚠ 这份清单是**实测基线** —— 源表表头变了(新报表模板), 这里要同步更新,
#:   否则下面的「登记的别名必须真实存在」用例会挡住改动(那是**故意的**:
#:   防止把不存在的列名登记进别名表 —— 登记了也永远命不中)。
REAL_SHOPEE_HEADERS = frozenset(
    {
        "日期",
        "访客数",
        "页面浏览数",
        "跳出率",
        "新访客",
        "现有访客",
        "新关注者",
        "平均停留时长",
        "平均页面访问数",
    }
)

REAL_TIKTOK_HEADERS = frozenset(
    {
        "日期",
        "GMV",
        "SKU 订单数",
        "去重商品曝光次数",
        "去重点击次数",
        "商品成交件数",
        "商品曝光次数",
        "商品点击量",
        "商品访客数",
        "商家直播 GMV",
        "商家直播间接 GMV",
        "商家视频 GMV",
        "商家视频间接 GMV",
        "客户数",
        "已退款的商品件数",
        "平均订单金额",
        "总成交额",
        "绑定账号直播归因 GMV",
        "绑定账号视频归因 GMV",
        "联盟视频归因 GMV",
        "订单数",
        "转化率",
        "达人直播 GMV",
        "达人直播归因 GMV",
        "达人直播间接 GMV",
        "达人视频 GMV",
        "达人视频间接 GMV",
        "页面浏览次数",
        "商品卡 GMV",
        "退款金额",
    }
)

#: 登记别名时必须**逐字**对上的真实表头(其余别名是英文/历史写法, 命不中也无害,
#: 但下面那组必须命中, 否则对应指标会恒为 NULL)。
#:
#: [*] 2026-11-10: ``visitor_count`` 的真实表头**分平台**——
#:   shopee「访客数」/ tiktok「商品访客数」(实测两边访客列名互斥)
#:   ⇒ 它改走**平台限定**登记, 见 :data:`PLATFORM_MUST_HIT_HEADERS`。
#:   (``product_visitor_count`` 已退出 analytics 域 —— 见
#:   :data:`test_product_visitors_are_registered_as_tiktok_visitor_count`。)
MUST_HIT_HEADERS = {
    "page_views": ("页面浏览数", "页面浏览次数"),
    "impressions": ("商品曝光次数",),
    "clicks": ("商品点击量",),
    "conversion_rate": ("转化率",),
    "order_count": ("订单数",),
    "sku_order_count": ("SKU 订单数",),
    "gmv": ("GMV",),
    "total_transaction_amount": ("总成交额",),
    "bounce_rate": ("跳出率",),
}

#: [*] 2026-11-10: **平台限定**的「必须命中」表头: 平台 -> 标准字段 -> 表头。
#:
#: 访客数必须成对登记 —— 别名合并规则里「某字段一旦登记了平台限定别名, 它的
#: 通用别名就整体不再登记」⇒ 只登记一边会把另一边**静默挤掉**(UV 变 NULL)。
PLATFORM_MUST_HIT_HEADERS = {
    "shopee": {"visitor_count": ("访客数",)},
    "tiktok": {"visitor_count": ("商品访客数",)},
}


def _view_sql() -> str:
    return VIEW_ASSET.read_text(encoding="utf-8", errors="replace")


# ── 一、别名清单口径 ────────────────────────────────────────────────────


def test_must_hit_aliases_are_registered_for_analytics_domain():
    """每个「必须命中」的真实表头都要登记在 analytics 域限定别名表里。"""
    for field, headers in MUST_HIT_HEADERS.items():
        aliases = set(ANALYTICS_SEMANTIC_ALIASES.get(field, ()))
        for header in headers:
            assert header in aliases, "{0} 没登记真实表头 {1!r}".format(field, header)


def test_must_hit_platform_aliases_are_registered_for_analytics_domain():
    """[*] 2026-11-10: 访客数的真实表头**分平台** ⇒ 必须登记在**平台限定**别名表。

    ⚠ 两个平台**都要**登记: 别名合并规则里, 某字段一旦登记了平台限定别名,
    它的通用别名就整体不再登记 ⇒ 只登记一边会把另一边**静默挤掉**。
    """
    for platform, per_field in PLATFORM_MUST_HIT_HEADERS.items():
        registered = ANALYTICS_PLATFORM_ALIASES.get(platform) or {}
        for field, headers in per_field.items():
            aliases = set(registered.get(field) or ())
            for header in headers:
                assert header in aliases, "{0} 的 {1} 没登记真实表头 {2!r}".format(
                    platform, field, header
                )


def test_registered_platform_chinese_headers_all_exist_in_real_source_tables():
    """平台限定别名表里登记的中文表头也必须是**真实存在**的列名(逐字)。

    [*] 2026-11-10: 平台限定别名表是「真实表头」的第二来源 ⇒ 同样要受
    「不许登记不存在的列名」这条约束(登记了但命不中 = 永远恒 NULL 且无人察觉)。
    """
    real_headers = REAL_SHOPEE_HEADERS | REAL_TIKTOK_HEADERS
    for per_platform in ANALYTICS_PLATFORM_ALIASES.values():
        for aliases in per_platform.values():
            for alias in aliases:
                if not re.search(r"[一-鿿]", alias):
                    continue
                if alias in real_headers:
                    continue
                assert (
                    alias in KNOWN_UNMATCHED_CHINESE_ALIASES
                ), "平台限定别名登记了不存在的列名 {0!r}".format(alias)


def test_registered_chinese_headers_all_exist_in_real_source_tables():
    """登记的中文别名必须是**真实存在**的列名(逐字)。

    登记一个不存在的列名 ⇒ 永远命不中 ⇒ 对应指标恒 NULL 且无人察觉。
    """
    real_headers = REAL_SHOPEE_HEADERS | REAL_TIKTOK_HEADERS
    # 全局别名(英文/历史写法)不在实测表头里, 这里只查**域限定**表里的中文项。
    for field, aliases in ANALYTICS_SEMANTIC_ALIASES.items():
        for alias in aliases:
            if not re.search(r"[一-鿿]", alias):
                continue
            if alias in real_headers:
                continue
            # 历史/推测性写法允许存在(命不中也无害), 但必须在下面这份
            # 「已知未命中」名单里, 否则就是新增了一个不存在的列名。
            assert (
                alias in KNOWN_UNMATCHED_CHINESE_ALIASES
            ), "{0} 登记了不存在的列名 {1!r}".format(field, alias)


#: 已知「登记了但真实表头里没有」的中文别名(历史写法)。
#:
#: ⚠ 这些别名在真实源表里**不存在** ⇒ 命中不了 ⇒ 对应指标靠别的别名取数。
#:   列在这里是为了「新增不存在的列名」能被用例挡住。
KNOWN_UNMATCHED_CHINESE_ALIASES = frozenset(
    {
        "统计日期",
        "交易日期",
        "日期时间",
        "店铺",
        "店铺id",
        "店铺名称",
        "访客量",
        "访问用户数",
        "页面浏览量",
        "商品浏览量",
        "浏览量",
        "曝光量",
        "曝光次数",
        "点击量",
        "点击次数",
        "跳失率",
        "订单量",
        "订单数量",
        "支付订单数",
        "成交订单数",
        "SKU订单量",
        "总交易金额",
        "成交额",
        "交易额",
    }
)


def test_one_column_name_maps_to_exactly_one_standard_field():
    """SSOT 硬约束: 一个列名只认一个标准字段。

    ``semantic.resolve_alias()`` 按 (domain, field) 查询 ⇒ 同一列名挂在两个
    字段上时, 两个字段会**各自**取到值 ⇒ 下游会把同一个数字当成两个
    不同的业务事实。
    """
    owners = {}
    for field, aliases in ANALYTICS_SEMANTIC_ALIASES.items():
        for alias in aliases:
            previous = owners.setdefault(alias, field)
            assert previous == field, "列名 {0!r} 同时归 {1} 与 {2}".format(
                alias, previous, field
            )


def test_product_visitors_are_registered_as_tiktok_visitor_count():
    """「商品访客数」归 **tiktok 的 visitor_count**, 不再归 product_visitor_count。

    [*] 2026-11-10(实测): tiktok 流量报表**没有**店铺级访客数, 唯一的访客
    列就是「商品访客数」⇒ 它**就是** tiktok 侧的 UV。
    架构契约(2026-05-26)早已批准这件事:
    「TikTok analytics explicitly maps 商品访客数 to canonical visitor_count」。

    ⚠ 但两平台的访客列名是**平台专有**的: shopee「访客数」、
    tiktok「商品访客数」⇒ 必须**平台限定**登记,
    不许进通用别名表(通用别名会让 tiktok 的数据被当成 shopee 口径命中)。
    ⇒ 口径本身经 2026-11-10 复核: 两平台都是「一店一天一行」的店铺当天访客量,
    **基本一致、可横向比较**。
    """
    tiktok_aliases = ANALYTICS_PLATFORM_ALIASES.get("tiktok") or {}
    shopee_aliases = ANALYTICS_PLATFORM_ALIASES.get("shopee") or {}

    assert "商品访客数" in (
        tiktok_aliases.get("visitor_count") or ()
    ), "tiktok 的「商品访客数」必须登记到 visitor_count"
    assert "访客数" in (
        shopee_aliases.get("visitor_count") or ()
    ), "shopee 的「访客数」必须登记到 visitor_count(两边必须对称)"

    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    assert "商品访客数" not in generic, "「商品访客数」不该留在通用别名表里"
    assert "访客数" not in generic, "「访客数」不该留在通用别名表里"

    assert (
        "product_visitor_count" not in ANALYTICS_SEMANTIC_ALIASES
    ), "product_visitor_count 已退出 analytics 域"


def test_click_rate_is_not_registered_because_no_platform_has_that_column():
    """click_rate 两个平台都没有这一列 ⇒ 不登记 ⇒ 恒 NULL(而不是 0)。"""
    assert "click_rate" not in ANALYTICS_SEMANTIC_ALIASES


def test_analytics_domain_is_covered_by_alias_seed():
    """analytics 域必须进别名 seed。

    此前该域**一条 builtin 行都没有** ⇒ ``resolve_alias()`` 只能命中 9 条
    模板确认行 ⇒ 域限定别名清单形同虚设。
    """
    from scripts.generate_semantic_alias_seed import SEED_DOMAINS

    assert "analytics" in SEED_DOMAINS
    alias_text = ALIAS_ASSET.read_text(encoding="utf-8", errors="replace")
    assert "'analytics'" in alias_text


# ── 二、视图取数与出口 ──────────────────────────────────────────────────


def test_analytics_view_reads_through_alias_registry():
    """取数必须走别名表(不再内联手写表头链)。"""
    sql_text = _view_sql()

    assert "semantic.resolve_alias(" in sql_text
    for field in MUST_HIT_HEADERS:
        assert "'{field}'".format(field=field) in sql_text
    # [*] 2026-11-10: visitor_count 改走平台限定登记, 但视图**照样**要取它
    #   (取数路径没变, 变的是「由哪一列取」) ⇒ 这条断言不许被顺手删掉。
    assert "'visitor_count'" in sql_text
    assert "'product_visitor_count'" in sql_text


def test_analytics_view_output_has_no_fake_zero_coalesce():
    """输出层不许再有 ``COALESCE(x, 0)`` —— 解析失败必须保留 NULL。"""
    sql_text = _view_sql()

    assert not re.search(r"COALESCE\(\s*\w+\s*,\s*0\s*\)\s+AS", sql_text)


def test_analytics_view_output_column_names_and_order_are_unchanged():
    """输出列名与列序一个都不能改(下游 mart 视图按列名取数)。"""
    sql_text = _view_sql()

    expected = [
        "visitor_count",
        "page_views",
        "impressions",
        "clicks",
        "click_rate",
        "conversion_rate",
        "order_count",
        "sku_order_count",
        "gmv",
        "total_transaction_amount",
        "product_visitor_count",
        "bounce_rate",
    ]
    tail = sql_text.rsplit("FROM deduplicated", 1)[0]
    positions = []
    for column in expected:
        marker = "{0} AS {0}".format(column)
        index = tail.rfind(marker)
        assert index > 0, "输出层缺列 {0}".format(column)
        positions.append(index)
    assert positions == sorted(positions), "输出列的顺序变了"


def test_analytics_view_does_not_read_raw_currency_or_literal_headers():
    """不许再内联字面量表头取数(那是旧实现的病根)。"""
    sql_text = _view_sql()

    for literal in (
        "raw_data->>'访客数'",
        "raw_data->>'页面浏览数'",
        "raw_data->>'页面浏览次数'",
        "raw_data->>'商品曝光次数'",
        "raw_data->>'商品点击量'",
        "raw_data->>'跳出率'",
        "raw_data->>'SKU 订单数'",
        "raw_data->>'总成交额'",
    ):
        assert literal not in sql_text, "视图仍在内联取 {0}".format(literal)


def test_analytics_fields_are_registered_in_dictionary():
    """被巡检的 analytics 标准字段必须在字典里有定义。"""
    fields = set(MUST_HIT_HEADERS)
    for per_field in PLATFORM_MUST_HIT_HEADERS.values():
        fields |= set(per_field)
    for field in fields:
        assert field in SEMANTIC_FIELD_DEFINITIONS, "标准字段 {0} 不在字典里".format(
            field
        )


def test_domain_alias_table_contains_analytics():
    """域限定别名表里必须有 analytics 域。"""
    assert "analytics" in DOMAIN_SEMANTIC_ALIASES
    assert DOMAIN_SEMANTIC_ALIASES["analytics"] is ANALYTICS_SEMANTIC_ALIASES
