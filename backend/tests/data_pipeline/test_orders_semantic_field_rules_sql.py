from pathlib import Path


def _block_before(sql_text: str, marker: str) -> str:
    return sql_text.split(marker, 1)[0].rsplit("COALESCE(", 1)[-1]


def test_orders_atomic_sql_keeps_paid_amount_sources_out_of_sales_amount_group():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS sales_amount_raw")

    forbidden = (
        "raw_data->>'实付金额'",
        "raw_data->>'买家实付金额'",
        "raw_data->>'买家支付(RMB)'",
        "raw_data->>'买家支付'",
        "raw_data->>'buyer_payment_rmb'",
        "raw_data->>'buyer_payment'",
    )
    for token in forbidden:
        assert token not in block


def test_orders_atomic_sql_maps_paid_amount_from_payment_fields_only():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS paid_amount_raw")

    required = (
        "raw_data->>'实付金额'",
        "raw_data->>'买家实付金额'",
        "raw_data->>'买家支付(RMB)'",
        "raw_data->>'买家支付'",
        "raw_data->>'buyer_payment_rmb'",
        "raw_data->>'buyer_payment'",
    )
    for token in required:
        assert token in block


def test_orders_atomic_sql_maps_sales_amount_from_sales_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS sales_amount_raw")

    required = (
        "raw_data->>'销售额'",
        "raw_data->>'销售金额'",
        "raw_data->>'GMV'",
        "raw_data->>'订单金额'",
        "raw_data->>'成交金额'",
        "raw_data->>'总收入'",
    )
    for token in required:
        assert token in block


def test_orders_atomic_sql_prefers_rmb_profit_sources():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS profit_raw")

    assert "raw_data->>'利润(RMB)'" in block
    assert "raw_data->>'profit_rmb'" in block
    assert "raw_data->>'利润'" in block
    assert "raw_data->>'profit'" in block
    assert block.index("raw_data->>'利润(RMB)'") < block.index("raw_data->>'利润'")
