from pathlib import Path


def _block_before(sql_text: str, marker: str) -> str:
    return sql_text.split(marker, 1)[0].rsplit("COALESCE(", 1)[-1]


def test_products_atomic_sql_maps_paid_confirmed_confirmed_order_sales_amount_aliases():
    sql_text = Path("sql/semantic/products_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS sales_amount_raw")

    required = (
        "raw_data->>'销售额（已付款订单）'",
        "raw_data->>'销售额（已确认订单）'",
        "raw_data->>'销售额（已确定订单）'",
    )
    for token in required:
        assert token in block


def test_products_atomic_sql_maps_paid_confirmed_order_count_aliases():
    sql_text = Path("sql/semantic/products_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS order_count_raw")

    required = (
        "raw_data->>'已付款订单'",
        "raw_data->>'已确认订单'",
        "raw_data->>'已确定订单'",
    )
    for token in required:
        assert token in block


def test_products_atomic_sql_maps_paid_confirmed_sales_volume_aliases():
    sql_text = Path("sql/semantic/products_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS sales_volume_raw")

    required = (
        "raw_data->>'件数（已付款订单）'",
        "raw_data->>'件数（已确认订单）'",
        "raw_data->>'件数（已确定订单）'",
    )
    for token in required:
        assert token in block


def test_products_atomic_sql_maps_paid_confirmed_conversion_rate_aliases():
    sql_text = Path("sql/semantic/products_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS conversion_rate_raw")

    required = (
        "raw_data->>'转化率（已付款订单）'",
        "raw_data->>'转化率（已确认订单）'",
        "raw_data->>'转化率（已确定订单）'",
    )
    for token in required:
        assert token in block
