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

    assert "raw_data->>'SKU 订单数'" not in _slice_before(sql_text, "AS order_count_raw")


def test_analytics_atomic_sql_does_not_merge_total_transaction_amount_into_gmv():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'总成交额'" not in _slice_before(sql_text, "AS gmv_raw")


def test_analytics_atomic_sql_maps_tiktok_product_visitor_count_into_visitor_count():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'商品访客数'" in _slice_before(sql_text, "AS visitor_count_raw")


def test_analytics_monthly_atomic_sql_exposes_split_fields():
    sql_text = Path("sql/semantic/analytics_monthly_atomic.sql").read_text(encoding="utf-8")

    for field_name in (
        "gmv",
        "order_count",
        "sku_order_count",
        "total_transaction_amount",
        "product_visitor_count",
    ):
        assert field_name in sql_text


def test_analytics_atomic_sql_maps_tiktok_product_visitor_count_to_visitor_count():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" in visitor_count_slice


def test_analytics_monthly_atomic_mv_maps_tiktok_product_visitor_count_to_visitor_count():
    sql_text = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(encoding="utf-8")

    visitor_count_slice = _slice_before(sql_text, "AS visitor_count_raw")
    assert "raw_data->>'商品访客数'" in visitor_count_slice
