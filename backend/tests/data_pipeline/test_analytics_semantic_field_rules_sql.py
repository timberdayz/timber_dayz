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
    """「商品访客数」**不许**混进 visitor_count。

    [*] 2026-11-08: tiktok 这份流量报表**没有**店铺级访客数, 源表里那个
    「商品访客数」是**商品级**的 ⇒ 旧实现用 CASE 硬塞进 visitor_count,
    是**静默的语义混淆**。现在它只归 product_visitor_count。
    """
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'商品访客数'" not in _slice_before(
        sql_text, "AS visitor_count_raw"
    )
    assert "raw_data->>'商品访客数'" not in sql_text
    # 取数一律走别名表 ⇒ 「商品访客数」由别名表决定落在哪个字段上。
    assert "semantic.resolve_alias(" in sql_text
    assert "'product_visitor_count'" in sql_text


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
    """商品访客数由**别名表**决定落点, 且只落 product_visitor_count。"""
    from backend.services.semantic_field_registry import ANALYTICS_SEMANTIC_ALIASES

    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" not in visitor_count_slice

    assert "商品访客数" in ANALYTICS_SEMANTIC_ALIASES["product_visitor_count"]
    assert "商品访客数" not in ANALYTICS_SEMANTIC_ALIASES["visitor_count"]


def test_analytics_monthly_atomic_mv_does_not_mix_product_visitor_count_into_visitor_count():
    """月度链与日/周链**同口径**: 商品访客数也不许混进 visitor_count。"""
    sql_text = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" not in visitor_count_slice
    assert "semantic.resolve_alias(" in sql_text
    assert "'product_visitor_count'" in sql_text
