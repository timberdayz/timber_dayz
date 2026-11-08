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
MUST_HIT_HEADERS = {
    "visitor_count": ("访客数",),
    "page_views": ("页面浏览数", "页面浏览次数"),
    "impressions": ("商品曝光次数",),
    "clicks": ("商品点击量",),
    "conversion_rate": ("转化率",),
    "order_count": ("订单数",),
    "sku_order_count": ("SKU 订单数",),
    "gmv": ("GMV",),
    "total_transaction_amount": ("总成交额",),
    "product_visitor_count": ("商品访客数",),
    "bounce_rate": ("跳出率",),
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


def test_product_visitor_count_is_not_mixed_into_visitor_count():
    """「商品访客数」只归 product_visitor_count, 不进 visitor_count。

    tiktok 这份流量报表**没有**店铺级访客数 ⇒ visitor_count 在 tiktok 上
    恒 NULL(如实反映)。以前视图里用 CASE 硬塞进去, 是**静默的语义混淆**。
    """
    assert "商品访客数" in ANALYTICS_SEMANTIC_ALIASES["product_visitor_count"]
    assert "商品访客数" not in ANALYTICS_SEMANTIC_ALIASES["visitor_count"]


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
    for field in MUST_HIT_HEADERS:
        assert field in SEMANTIC_FIELD_DEFINITIONS, "标准字段 {0} 不在字典里".format(
            field
        )


def test_domain_alias_table_contains_analytics():
    """域限定别名表里必须有 analytics 域。"""
    assert "analytics" in DOMAIN_SEMANTIC_ALIASES
    assert DOMAIN_SEMANTIC_ALIASES["analytics"] is ANALYTICS_SEMANTIC_ALIASES
