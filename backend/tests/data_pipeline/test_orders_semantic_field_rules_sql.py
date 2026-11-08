from pathlib import Path


def _block_before(sql_text: str, marker: str) -> str:
    return sql_text.split(marker, 1)[0].rsplit("COALESCE(", 1)[-1]


def test_orders_atomic_sql_keeps_paid_amount_sources_out_of_sales_amount_group():
    """销售额已废止 —— 出口恒 NULL, 不许再从任何列取数。

    [*] 2026-11-08: 源表**没有**「销售额/成交金额」这一列, 以前命中的是
    tiktok 的「总收入」(原币) ⇒ 与 `paid_amount` 抢同一个业务含义、币种还不对。
    ⇒ `sales_amount` 废止(见 ``semantic_field_registry.ORDER_RETIRED_FIELDS``),
    视图保留列但恒 NULL(``CREATE OR REPLACE VIEW`` 不能删列)。
    """
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS sales_amount_raw")

    forbidden = (
        "raw_data->>'销售额'",
        "raw_data->>'销售金额'",
        "raw_data->>'GMV'",
        "raw_data->>'订单金额'",
        "raw_data->>'成交金额'",
        "raw_data->>'总收入'",
        "raw_data->>'sales_amount'",
    )
    for token in forbidden:
        assert token not in block, f"销售额已废止, 不许再取 {token!r}"

    assert "NULL::text AS sales_amount_raw" in sql_text


def test_orders_atomic_sql_maps_paid_amount_from_payment_fields_only():
    """买家实付只从别名表取 —— 别名表里只登 (RMB) 变体。

    [*] 2026-11-08 实测: 源表里「买家支付」(原币) 与「买家支付(RMB)」(人民币)
    **同时存在**, 均值差约 3 倍(240.11 vs 72.03)。手写链的兜底会落到裸名列
    ⇒ 混币种 ⇒ 裸名列**不接任何标准字段**。
    """
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS paid_amount_raw")

    assert (
        "semantic.resolve_alias(raw_data, data_domain, 'paid_amount', platform_code, granularity)"
        in block
    )

    from backend.services.semantic_field_registry import ORDER_PLATFORM_ALIASES

    assert ORDER_PLATFORM_ALIASES["shopee"]["paid_amount"] == ("买家支付(RMB)",)
    assert ORDER_PLATFORM_ALIASES["tiktok"]["paid_amount"] == ("买家实付金额(RMB)",)

    # ⚠ 裸名列(原币)不许出现在取数表达式里
    for token in (
        "raw_data->>'买家支付'",
        "raw_data->>'买家实付金额'",
        "raw_data->>'实付金额'",
        "raw_data->>'buyer_payment'",
    ):
        assert token not in sql_text, f"裸名列(原币)不许被取数: {token!r}"


def test_orders_atomic_sql_maps_sales_amount_from_sales_fields():
    """销售额已废止 —— 出口恒 NULL。"""
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "NULL::text AS sales_amount_raw" in sql_text
    # 出口也不再 COALESCE 成 0(视图不能删列, 但不许输出 0 伪值)
    assert "COALESCE(sales_amount, 0) AS sales_amount" not in sql_text

    from backend.services.semantic_field_registry import (
        ORDER_RETIRED_FIELDS,
        ORDER_STANDARD_FIELDS,
    )

    assert "sales_amount" in ORDER_RETIRED_FIELDS
    assert "sales_amount" not in ORDER_STANDARD_FIELDS


def test_orders_atomic_sql_prefers_rmb_profit_sources():
    """利润只从「利润(RMB)」取 —— 裸名「利润」是原币列, 不许接标准字段。"""
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS profit_raw")

    assert (
        "semantic.resolve_alias(raw_data, data_domain, 'profit', platform_code, granularity)"
        in block
    )

    from backend.services.semantic_field_registry import ORDER_SEMANTIC_ALIASES

    # 2026-11-08: orders 域是**封闭域** —— 只登「利润(RMB)」这个带币种的变体；
    # 另允许**纯 ASCII** 别名（英文无币种歧义，逐字匹配同样安全）。
    assert "利润(RMB)" in ORDER_SEMANTIC_ALIASES["profit"]
    assert (
        "利润" not in ORDER_SEMANTIC_ALIASES["profit"]
    ), "裸名「利润」是原币列，不许登记进封闭域别名表"
    assert "profit_amount" in ORDER_SEMANTIC_ALIASES["profit"]
    assert "raw_data->>'利润'" not in sql_text, "裸名列(原币)不许被取数"
