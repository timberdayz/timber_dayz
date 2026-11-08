"""Metabase 订单模型的语义层取数守护(B1, 2026-11-08)。

背景
----
``sql/metabase_models/orders_model.sql`` 是 BI 侧的独立消费方, 以前自己手写
一份 ``COALESCE(raw_data->>'A', raw_data->>'B', ...)`` 取数链 ⇒ **绕过语义层**。

危害(实测, 改造前后同一份开发库跑同一个模型):
* shopee「实付金额」改造前合计 **0.00** —— 手写链找的是「实付金额/买家实付金额/
  paid_amount/Paid Amount」, 而 shopee 的真实列名是「买家支付(RMB)」⇒ **一个都
  找不到** ⇒ 整列 0。改造后 = **1,993,149.50**(人民币)。
* tiktok「实付金额」改造前合计 **1,458,557.59** —— 命中的是**原币**列
  ⇒ 是改造后 **402,284.04**(人民币)的 3.63 倍 ⇒ **混币种**。

本文件守住三件事:
1. **BI 契约**: 输出列名一个都不能变(外部 dashboard / 卡片按列名引用);
2. **取数口径**: 已登记字段必须走 ``semantic.resolve_alias()``;
   字典**未登记**的字段保留手写链(``resolve_alias`` 认不出它们);
3. **不装 0**: 输出层不再有 ``COALESCE(x, 0)``(缺项 = NULL = 「不知道」)。
"""

from __future__ import annotations

import re
from pathlib import Path

MODEL_PATH = Path("sql/metabase_models/orders_model.sql")

#: 改造前(HEAD)的输出列清单 —— **BI 契约**, 一个都不能少、不能多、不能换顺序。
EXPECTED_OUTPUT_COLUMNS = (
    "platform_code",
    "shop_id",
    "data_domain",
    "granularity",
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
    "order_id",
    "order_status",
    "sales_amount",
    "paid_amount",
    "product_original_price",
    "estimated_settlement_amount",
    "profit",
    "purchase_amount",
    "order_original_amount",
    "warehouse_operation_fee",
    "shipping_fee",
    "promotion_fee",
    "platform_commission",
    "platform_deduction_fee",
    "platform_voucher",
    "platform_service_fee",
    "platform_total_cost_derived",
    "platform_total_cost_itemized",
    "order_time",
    "payment_time",
    "order_date",
    "product_name",
    "product_id",
    "platform_sku",
    "sku_id",
    "product_sku",
    "product_type",
    "outbound_warehouse",
    "buyer_count",
    "order_count",
    "product_quantity",
    "raw_data",
    "header_columns",
    "data_hash",
    "ingest_timestamp",
    "currency_code",
)

#: 字典已登记 ⇒ 取数走 resolve_alias 的字段(模型列名 → 语义键)。
RESOLVED_BY_ALIAS_TABLE = {
    "order_id": "order_id",
    "order_status": "order_status",
    "paid_amount": "paid_amount",
    "estimated_settlement_amount": "estimated_settlement_amount",
    "profit": "profit",
    "order_time": "order_date",
    "product_name": "product_name",
    "product_id": "product_id",
    "platform_sku": "platform_sku",
    "sku_id": "sku_id",
    "product_sku": "product_sku",
    "buyer_count": "buyer_count",
    "product_quantity": "sales_volume",
    "purchase_amount": "purchase_amount",
    "order_original_amount": "order_original_amount",
    "warehouse_operation_fee": "warehouse_operation_fee",
    "shipping_fee": "shipping_fee",
    "promotion_fee": "promotion_fee",
    "platform_commission": "platform_commission",
    "platform_deduction_fee": "platform_deduction_fee",
    "platform_voucher": "platform_voucher",
    "platform_service_fee": "platform_service_fee",
}

#: 字典**未登记** ⇒ 必须保留手写链(resolve_alias 认不出它们)。
#: - ``product_original_price`` / ``payment_time`` / ``product_type`` /
#:   ``outbound_warehouse`` / ``order_count``: 字典里没有对应标准字段;
#: - ``order_date``: 源表**压根没有**「订单日期」「日期」这一列
#:   (实测两平台只有「下单时间/付款时间/发货时间/结算时间/采购时间」)
#:   ⇒ 本来就取不到值, 保留手写链(行为不变)。
KEPT_MANUAL_COLUMNS = (
    "product_original_price",
    "payment_time",
    "order_date",
    "product_type",
    "outbound_warehouse",
    "order_count",
)


def _model_text() -> str:
    return MODEL_PATH.read_text(encoding="utf-8", errors="replace")


def _split_top_level(text: str):
    """按**括号深度**切分顶层逗号分隔项。

    形如 ``COALESCE(sales_amount, 0) AS sales_amount`` 的列内部含逗号
    ⇒ 朴素的 ``split(",")`` 会把一列切成两半。
    """
    items = []
    depth = 0
    current = []
    in_single = False
    in_double = False
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append("".join(current))
                current = []
                continue
        current.append(ch)
    if "".join(current).strip():
        items.append("".join(current))
    return items


def _output_columns(sql_text: str):
    tail = sql_text.rsplit("FROM with_shop_resolved", 1)[0]
    idx = tail.rfind("\nSELECT")
    assert idx > 0, "找不到最终 SELECT 段"
    segment = tail[idx:]
    segment = segment[segment.index("SELECT") + len("SELECT") :]
    body = "\n".join(line.split("--", 1)[0] for line in segment.split("\n"))
    columns = []
    for item in _split_top_level(body):
        item = item.strip()
        if not item:
            continue
        matched = re.search(r"\bAS\s+(\w+)\s*$", item)
        if matched:
            columns.append(matched.group(1))
            continue
        matched = re.match(r"^(\w+)$", item)
        assert matched, "无法解析输出列: %r" % item
        columns.append(matched.group(1))
    return columns


def test_metabase_model_output_columns_are_unchanged():
    """BI 契约: 输出列名与顺序一个都不能变。"""
    assert _output_columns(_model_text()) == list(EXPECTED_OUTPUT_COLUMNS)


def test_registered_fields_resolve_through_the_alias_table():
    """已登记字段的取数**必须**走 ``semantic.resolve_alias()``。"""
    sql_text = _model_text()
    for column, standard_field in RESOLVED_BY_ALIAS_TABLE.items():
        expected = (
            "semantic.resolve_alias(raw_data, data_domain, '{std}', "
            "platform_code, granularity) AS {col}_raw".format(
                std=standard_field, col=column
            )
        )
        assert expected in sql_text, "{} 没有走别名表".format(column)
        # 该列不得再留手写取数链
        for line in sql_text.split("\n"):
            if "raw_data->>" not in line:
                continue
            assert (
                "AS {}_raw,".format(column) not in line
            ), "{} 还留着手写取数链(会混币种)".format(column)


def test_unregistered_fields_keep_the_manual_chain():
    """字典未登记的字段**保留**手写链 —— 不能瞎换成 resolve_alias。"""
    sql_text = _model_text()
    for column in KEPT_MANUAL_COLUMNS:
        manual_lines = [
            line
            for line in sql_text.split("\n")
            if line.strip().endswith("AS {}_raw,".format(column))
        ]
        assert manual_lines, column
        for line in manual_lines:
            assert (
                "resolve_alias" not in line
            ), "{} 不该被换成 resolve_alias(字典未登记, 它认不出)".format(column)
            assert "raw_data->>" in line, column


def test_retired_sales_amount_is_null():
    """``sales_amount`` 已废止 ⇒ 恒 NULL(源表没有「销售额」这一列)。"""
    sql_text = _model_text()
    assert "NULL::text AS sales_amount_raw" in sql_text
    assert "COALESCE(sales_amount, 0)" not in sql_text


def test_output_layer_does_not_fake_zero():
    """输出层不再有 ``COALESCE(x, 0)`` —— 「取不到数」= NULL, 不冒充 0。"""
    sql_text = _model_text()
    hits = re.findall(r"COALESCE\((\w+), 0\)", sql_text)
    assert hits == [], hits
