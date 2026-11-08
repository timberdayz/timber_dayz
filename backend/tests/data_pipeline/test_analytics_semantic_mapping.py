from pathlib import Path


def test_analytics_atomic_sql_exists_and_creates_semantic_view():
    sql_path = Path("sql/semantic/analytics_atomic.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.fact_analytics_atomic AS" in sql_text


def test_analytics_atomic_sql_exposes_core_standard_fields():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    for field_name in (
        "platform_code",
        "shop_id",
        "metric_date",
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
        "currency_code",
        "data_hash",
        "ingest_timestamp",
    ):
        assert field_name in sql_text


def test_analytics_sql_supports_shopee_and_tiktok_page_view_aliases():
    """页面浏览数(shopee) / 页面浏览次数(tiktok) 都必须能被解析到。

    [*] 2026-11-08: 取数改走别名表 ⇒ 断言从「SQL 里内联这两个表头」
    改成「**别名表里登记了这两个真实表头** + 两条链都走 resolve_alias」
    —— 更强: 内联写法根本不该再出现。
    """
    from backend.services.semantic_field_registry import ANALYTICS_SEMANTIC_ALIASES

    daily_sql = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    monthly_sql = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )

    page_view_shopee = "".join(chr(c) for c in [39029, 38754, 27983, 35272, 25968])
    page_view_tiktok = "".join(
        chr(c) for c in [39029, 38754, 27983, 35272, 27425, 25968]
    )

    assert page_view_shopee in ANALYTICS_SEMANTIC_ALIASES["page_views"]
    assert page_view_tiktok in ANALYTICS_SEMANTIC_ALIASES["page_views"]

    for sql_text in (daily_sql, monthly_sql):
        assert "semantic.resolve_alias(" in sql_text
        assert "'page_views'" in sql_text
        # 内联取表头的老写法不该再出现。
        assert "raw_data->>'{0}'".format(page_view_shopee) not in sql_text
        assert "raw_data->>'{0}'".format(page_view_tiktok) not in sql_text


def test_analytics_sql_does_not_register_unmeasured_store_page_visit_column():
    """「店铺页面访问量」在真实源表里**不存在** ⇒ 不许登记进别名表。

    [*] 2026-11-08: 旧实现把它当作访客列的候选之一(推测性写法)。
    实测(开发库 2026-11-08)两个平台的 analytics 源表都**没有**这一列 ⇒
    登记它没有任何收益, 只会让别名表与真实表头脱节。
    ⇒ 现在断言它**不在**别名表里(比旧断言更强)。
    """
    from backend.services.semantic_field_registry import ANALYTICS_SEMANTIC_ALIASES

    tiktok_store_page_visit = "".join(
        chr(c) for c in [24215, 38138, 39029, 38754, 35775, 38382, 37327]
    )
    registered = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        registered.update(aliases)
    assert tiktok_store_page_visit not in registered


def test_analytics_sql_resolves_product_visitors_as_product_visitor_count():
    """「商品访客数」归 ``product_visitor_count``(商品级), 不进 visitor_count。"""
    from backend.services.semantic_field_registry import ANALYTICS_SEMANTIC_ALIASES

    daily_sql = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    monthly_mv_sql = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )

    tiktok_product_visitors = "".join(
        chr(c) for c in [21830, 21697, 35775, 23458, 25968]
    )
    assert (
        tiktok_product_visitors in ANALYTICS_SEMANTIC_ALIASES["product_visitor_count"]
    )
    assert tiktok_product_visitors not in ANALYTICS_SEMANTIC_ALIASES["visitor_count"]

    for sql_text in (daily_sql, monthly_mv_sql):
        assert "semantic.resolve_alias(" in sql_text
        assert "'product_visitor_count'" in sql_text
