from pathlib import Path


def _slice_before(sql_text: str, marker: str) -> str:
    return sql_text.split(marker)[0]


def test_analytics_atomic_sql_exposes_split_fields_for_tiktok_same_file_metrics():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "sku_order_count" in sql_text
    assert "total_transaction_amount" in sql_text
    assert "product_visitor_count" in sql_text


def test_analytics_atomic_sql_does_not_merge_sku_order_count_into_order_count():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'SKU 订单数'" not in _slice_before(
        sql_text, "AS order_count_raw"
    )


def test_analytics_atomic_sql_does_not_merge_total_transaction_amount_into_gmv():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'总成交额'" not in _slice_before(sql_text, "AS gmv_raw")


def test_analytics_atomic_sql_does_not_mix_product_visitor_count_into_visitor_count():
    """「商品访客数」**不许**在 SQL 里内联硬塞进 visitor_count。

    [*] 2026-11-10: 落点改由**别名表**决定 —— tiktok 的「商品访客数」登记到
    ``visitor_count``(平台限定), 因为它**就是** tiktok 侧唯一的访客列
    (实测 1374 行 raw_data key 里没有店铺级访客数这一列)。
    ⚠ 但两平台口径不同(shopee 全店去重访客人数 / tiktok 商品访客人次)
    ⇒ 落点由别名表的**平台维度**保证, SQL 里不许硬编码。

    ⇒ 断言: SQL 里既不许内联这个表头, 也不许内联另一个表头;
    取数一律走 ``semantic.resolve_alias()``。
    """
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'商品访客数'" not in _slice_before(
        sql_text, "AS visitor_count_raw"
    )
    assert "raw_data->>'商品访客数'" not in sql_text
    assert "raw_data->>'访客数'" not in sql_text
    # 取数一律走别名表 ⇒ 「商品访客数」由别名表决定落在哪个字段上。
    assert "semantic.resolve_alias(" in sql_text
    assert "'visitor_count'" in sql_text


def test_analytics_monthly_atomic_sql_exposes_split_fields():
    sql_text = Path("sql/semantic/analytics_monthly_atomic.sql").read_text(
        encoding="utf-8"
    )

    for field_name in (
        "gmv",
        "order_count",
        "sku_order_count",
        "total_transaction_amount",
        "product_visitor_count",
    ):
        assert field_name in sql_text


def test_analytics_atomic_sql_resolves_product_visitor_count_by_alias_registry():
    """商品访客数的落点由**别名表**决定: tiktok 侧归 ``visitor_count``。

    [*] 2026-11-10: tiktok 流量报表**没有**店铺级访客数, 唯一的访客列就是
    「商品访客数」⇒ 它就是 tiktok 侧的 UV(架构契约 2026-05-26 已批准)。
    ⇒ 但必须是**平台限定**登记 —— 通用别名会让两个平台串口径。
    """
    from backend.services.semantic_field_registry import (
        ANALYTICS_PLATFORM_ALIASES,
        ANALYTICS_SEMANTIC_ALIASES,
    )

    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" not in visitor_count_slice
    assert "raw_data->>'访客数'" not in visitor_count_slice

    tiktok_aliases = ANALYTICS_PLATFORM_ALIASES.get("tiktok") or {}
    shopee_aliases = ANALYTICS_PLATFORM_ALIASES.get("shopee") or {}
    assert "商品访客数" in (tiktok_aliases.get("visitor_count") or ())
    assert "访客数" in (shopee_aliases.get("visitor_count") or ())

    generic = set()
    for aliases in ANALYTICS_SEMANTIC_ALIASES.values():
        generic.update(aliases)
    assert "商品访客数" not in generic
    assert "访客数" not in generic


def test_analytics_monthly_atomic_mv_does_not_mix_product_visitor_count_into_visitor_count():
    """月度链与日/周链**同口径**: 访客列同样不许在 SQL 里内联。

    [*] 2026-11-10: 月度链的落点与日/周链**完全一致** —— tiktok 的
    「商品访客数」归 ``visitor_count``(平台限定), 且两平台口径不同
    (shopee 全店去重访客人数 / tiktok 商品访客人次)⇒ 不许内联硬塞。
    """
    from backend.services.semantic_field_registry import ANALYTICS_PLATFORM_ALIASES

    sql_text = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" not in visitor_count_slice
    assert "raw_data->>'访客数'" not in visitor_count_slice
    assert "semantic.resolve_alias(" in sql_text
    assert "'visitor_count'" in sql_text

    tiktok_aliases = ANALYTICS_PLATFORM_ALIASES.get("tiktok") or {}
    assert "商品访客数" in (tiktok_aliases.get("visitor_count") or ())
