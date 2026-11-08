#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 4 · 入库归一化派生的验收测试。

覆盖三条验收线:
  1. ``ORDER_LEVEL_AMOUNT_FIELDS`` 从**字典派生**, 且覆盖订单域真实存在的
     金额表头(含各平台列名);
  2. 多 SKU 订单**只有第 1 行带整单金额**(虚增为 0);
  3. 订单号缺失的行**独立成行**, 不与相邻订单错配。
"""

from __future__ import annotations

from backend.services.orders_ingestion_normalizer import (
    MISSING_ORDER_ID_PREFIX,
    ORDER_LEVEL_AMOUNT_FIELDS,
    merge_orders_raw_data_prefer_non_empty,
    prepare_orders_rows_for_b_class,
)
from backend.services.semantic_field_registry import (
    ORDER_LEVEL_QUANTITY_FIELDS,
    SEMANTIC_FIELD_DEFINITIONS,
)


# ── 1. 派生口径 ────────────────────────────────────────────────────────

#: 订单域真实存在的**订单级金额表头**(2026-11 开发库实测 raw_data key)。
#: ⚠ 只放**订单级**的列(源表合并单元格 ⇒ 同一订单内取值恒定或仅首行有值),
#:    且必须是**字典已登记**的列 —— 见下面的「登记缺口」用例。
REAL_ORDER_LEVEL_AMOUNT_HEADERS = (
    # shopee
    "买家支付(RMB)",
    "买家支付",
    "订单原始金额(RMB)",
    "订单原始金额",
    "服务费(RMB)",
    "服务费",
    "Shopee平台佣金(RMB)",
    "Shopee平台佣金",
    "卖家支付运费(RMB)",
    "卖家支付运费",
    "Shopee voucher(RMB)",
    "Shopee voucher",
    "卖家voucher(RMB)",
    "卖家voucher",
    "仓库操作费(RMB)",
    "仓库操作费",
    "广告成本(RMB)",
    "广告成本",
    "退款金额(RMB)",
    "退款金额",
    "预估回款金额(RMB)",
    "预估回款金额",
    "已结算金额(RMB)",
    "已结算金额",
    "利润(RMB)",
    "利润",
    # tiktok
    "买家实付金额(RMB)",
    "买家实付金额",
    "TikTok 平台佣金(RMB)",
    "TikTok 平台佣金",
    "商家运费(RMB)",
    "商家运费",
    # 2026-11-08 补登: 联盟/达人佣金、卖家总收入、卖家实际到手
    "联盟佣金(RMB)",
    "达人佣金(RMB)",
    "总收入(RMB)",
    "回款金额(RMB)",
)

#: 真实存在、粒度为**订单级**、但**字典尚未登记**的列。
#:
#: ⇒ 当前不在派生集合里(派生只认字典已登记的列名)。
#: ⇒ 字典补登标准字段后会自动纳入(派生即单一事实源), 这条断言会失败,
#:    提醒把对应列名补进上面的覆盖清单。
UNREGISTERED_ORDER_LEVEL_HEADERS = (
    # ⚠ 真实存在、订单级、但字典**完全未登记**且归一化后不同名的列
    # (shopee 独有; 实测 shopee 周/月粒度每单一行 ⇒ 订单级)。
    # ⇒ 它**不在**派生集合里 —— 派生只认字典已登记的列名。
    "3pl运费折扣(RMB)",
)


def test_derived_amount_fields_cover_real_order_level_amount_headers():
    """派生集合必须覆盖订单域真实存在的订单级金额表头(含各平台列名)。"""
    missing = [
        header
        for header in REAL_ORDER_LEVEL_AMOUNT_HEADERS
        if header not in ORDER_LEVEL_AMOUNT_FIELDS
    ]

    assert missing == []


def test_derived_amount_fields_come_from_dictionary_markers():
    """派生集合的每个成员都能追溯到字典的订单级标记 + orders 域登记列名。"""
    assert "order_level_amount" in SEMANTIC_FIELD_DEFINITIONS["paid_amount"]
    assert SEMANTIC_FIELD_DEFINITIONS["paid_amount"]["order_level_amount"] is True

    # 语义键本身也在集合里(入库行可能直接用语义键做 key)
    assert "paid_amount" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "profit_rmb" in ORDER_LEVEL_AMOUNT_FIELDS

    # 域限定的真实列名
    assert "仓库操作费(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "退款金额(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "预估回款金额(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS

    # 平台分别的真实列名
    assert "Shopee平台佣金(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "卖家支付运费(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "Shopee voucher(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "卖家voucher(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "买家实付金额(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "TikTok 平台佣金(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "商家运费(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS

    # 2026-11-08 补登后自动纳入(派生即单一事实源):
    # 「联盟/达人佣金」「卖家总收入」「卖家实际到手」三族。
    assert "联盟佣金(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "达人佣金(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "总收入(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS
    assert "回款金额(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS


def test_unregistered_real_order_level_columns_are_a_documented_gap():
    """真实存在但**字典未登记**的订单级列 ⇒ 当前不在派生集合里。

    字典补登标准字段后会自动纳入(派生即单一事实源)⇒ 这条断言失败时,
    说明要把对应列名补进上面的覆盖清单。
    """
    assert set(UNREGISTERED_ORDER_LEVEL_HEADERS).isdisjoint(ORDER_LEVEL_AMOUNT_FIELDS)


def test_derived_amount_fields_cover_every_registered_order_level_alias():
    """字典里标了订单级标记的字段, 其**每个**登记别名都必须在派生集合里。

    派生集合是从字典派生的 ⇒ 这条断言守的是「派生没有漏项」:
    字典加了字段/别名却没进派生 ⇒ 多 SKU 订单的第 2+ 行不会被清空
    ⇒ 整单金额被**重复计入** ⇒ 虚增。
    """
    from backend.services.semantic_field_registry import (
        DOMAIN_PLATFORM_SEMANTIC_ALIASES,
        DOMAIN_SEMANTIC_ALIASES,
        ORDER_LEVEL_AMOUNT_PLATFORM_EXCEPTIONS,
        SEMANTIC_FIELD_DEFINITIONS,
    )

    # 平台例外(如 tiktok 的「产品原价(RMB)」是**行级单价**)不在派生集合里 ——
    # 这是**有意的**(见 test_tiktok_product_original_amount_is_excluded_as_row_level)。
    exceptions = set(ORDER_LEVEL_AMOUNT_PLATFORM_EXCEPTIONS)

    missing = []
    for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
        if meta.get("domain") != "orders" or not meta.get("order_level_amount"):
            continue
        names = [key]
        names += list(meta.get("aliases") or [])
        names += list(DOMAIN_SEMANTIC_ALIASES.get("orders", {}).get(key, ()))
        for platform_code, per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(
            "orders", {}
        ).items():
            if (platform_code, key) in exceptions:
                continue
            names += list(per_platform.get(key, ()))
        for name in names:
            if name not in ORDER_LEVEL_AMOUNT_FIELDS:
                missing.append((key, name))

    assert missing == [], missing


def test_normalized_siblings_are_collected_together():
    """归一化同族的**裸名**也跟着进派生集合。

    ``normalize_semantic_alias("联盟佣金(RMB)") == "联盟佣金"``
    ⇒ 同族裸名一起进来, 清空时同族一起清 ⇒ 不会同族重复计入。

    ⚠ 裸名本身**不登记**进字典(orders 域是封闭域, 只登 ``(RMB)`` 变体,
    裸名是原币列) ⇒ 登记它 = 混币种。
    """
    from backend.services.semantic_field_registry import (
        ORDER_PLATFORM_ALIASES,
        ORDER_SEMANTIC_ALIASES,
        normalize_semantic_alias,
    )

    assert normalize_semantic_alias("联盟佣金(RMB)") == "联盟佣金"
    assert "联盟佣金" in ORDER_LEVEL_AMOUNT_FIELDS

    registered_names = set(ORDER_SEMANTIC_ALIASES.get("affiliate_commission", ()))
    for per_platform in ORDER_PLATFORM_ALIASES.values():
        registered_names.update(per_platform.get("affiliate_commission", ()))
    assert "联盟佣金" not in registered_names
    assert "联盟佣金(RMB)" in registered_names


def test_derived_amount_fields_exclude_row_level_columns():
    """行级列(采购成本、销售数量)不得进入清空集合, 否则会少算。"""
    # 采购成本: 字典里 domain=products, 且实测同一订单内逐行不同 ⇒ 行级
    assert "采购成本(RMB)" not in ORDER_LEVEL_AMOUNT_FIELDS
    assert "purchase_amount" not in ORDER_LEVEL_AMOUNT_FIELDS
    # 销售数量: 实测同一订单内取值不同(1/2/1/4/4/2/3/3)⇒ 行级件数
    assert "销售数量" not in ORDER_LEVEL_AMOUNT_FIELDS
    # 数量集合单独登记, 便于巡检时看到「字典口径 vs 实测粒度」的差异
    assert "销售数量" in ORDER_LEVEL_QUANTITY_FIELDS


def test_tiktok_product_original_amount_is_excluded_as_row_level():
    """tiktok「产品原价(RMB)」是行级单价 ⇒ 清空第 2+ 行会少算。"""
    assert "产品原价(RMB)" not in ORDER_LEVEL_AMOUNT_FIELDS
    # shopee 的「订单原始金额(RMB)」是合并单元格 ⇒ 仍然要清空
    assert "订单原始金额(RMB)" in ORDER_LEVEL_AMOUNT_FIELDS


# ── 2. 多 SKU 订单: 只有第 1 行带整单金额 ──────────────────────────────


def test_multi_sku_order_keeps_order_level_amounts_on_first_row_only():
    """同订单 3 个 SKU ⇒ 只有第 1 行带订单级金额, 虚增为 0。"""
    rows = [
        {
            "订单编号": "2606131JJFE29C",
            "平台SKU": "SKU-A",
            "买家支付(RMB)": "100.14",
            "利润(RMB)": "55.33",
            "仓库操作费(RMB)": "3.20",
            "广告成本(RMB)": "1.10",
            "预估回款金额(RMB)": "80.00",
            "已结算金额(RMB)": "75.00",
            "退款金额(RMB)": "0.00",
            "服务费(RMB)": "2.00",
            "Shopee平台佣金(RMB)": "6.00",
            "卖家支付运费(RMB)": "-4.00",
            "订单原始金额(RMB)": "120.00",
            "销售数量": "3",
            "采购成本(RMB)": "10.00",
        },
        {
            "订单编号": "2606131JJFE29C",
            "平台SKU": "SKU-B",
            "买家支付(RMB)": "100.14",
            "利润(RMB)": "55.33",
            "仓库操作费(RMB)": "3.20",
            "广告成本(RMB)": "1.10",
            "预估回款金额(RMB)": "80.00",
            "已结算金额(RMB)": "75.00",
            "退款金额(RMB)": "0.00",
            "服务费(RMB)": "2.00",
            "Shopee平台佣金(RMB)": "6.00",
            "卖家支付运费(RMB)": "-4.00",
            "订单原始金额(RMB)": "120.00",
            "销售数量": "3",
            "采购成本(RMB)": "12.00",
        },
        {
            "订单编号": "2606131JJFE29C",
            "平台SKU": "SKU-C",
            "买家支付(RMB)": "100.14",
            "利润(RMB)": "55.33",
            "仓库操作费(RMB)": "3.20",
            "广告成本(RMB)": "1.10",
            "预估回款金额(RMB)": "80.00",
            "已结算金额(RMB)": "75.00",
            "退款金额(RMB)": "0.00",
            "服务费(RMB)": "2.00",
            "Shopee平台佣金(RMB)": "6.00",
            "卖家支付运费(RMB)": "-4.00",
            "订单原始金额(RMB)": "120.00",
            "销售数量": "3",
            "采购成本(RMB)": "14.00",
        },
    ]

    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    order_level_headers = [
        "买家支付(RMB)",
        "利润(RMB)",
        "仓库操作费(RMB)",
        "广告成本(RMB)",
        "预估回款金额(RMB)",
        "已结算金额(RMB)",
        "退款金额(RMB)",
        "服务费(RMB)",
        "Shopee平台佣金(RMB)",
        "卖家支付运费(RMB)",
        "订单原始金额(RMB)",
    ]

    # 第 1 行保留整单金额, 第 2/3 行清空 ⇒ 按行 SUM 不会虚增
    for header in order_level_headers:
        assert prepared_rows[0][header] != "", header
        assert prepared_rows[1][header] == "", header
        assert prepared_rows[2][header] == "", header

    # 行级列不动: 销售数量(件数)与采购成本(行级成本)
    assert [row["销售数量"] for row in prepared_rows] == ["3", "3", "3"]
    assert [row["采购成本(RMB)"] for row in prepared_rows] == [
        "10.00",
        "12.00",
        "14.00",
    ]

    # 明细行号只加在第 2+ 行
    assert identity_values == [{}, {"_source_line_index": 2}, {"_source_line_index": 3}]


def test_multi_sku_order_amount_sum_is_not_inflated():
    """按行求和的订单级金额 == 整单金额(虚增为 0)。"""
    rows = [
        {
            "订单编号": "SO-INFLATE-1",
            "平台SKU": "SKU-A",
            "买家支付(RMB)": "371.32",
            "服务费(RMB)": "10.73",
        },
        {
            "订单编号": "SO-INFLATE-1",
            "平台SKU": "SKU-B",
            "买家支付(RMB)": "371.32",
            "服务费(RMB)": "10.73",
        },
    ]

    prepared_rows, _ = prepare_orders_rows_for_b_class(rows)

    paid_sum = sum(float(row["买家支付(RMB)"] or 0) for row in prepared_rows)
    fee_sum = sum(float(row["服务费(RMB)"] or 0) for row in prepared_rows)

    assert paid_sum == 371.32
    assert fee_sum == 10.73


# ── 3. 订单号缺失: 独立成行, 不跨单错配 ────────────────────────────────


def test_missing_order_id_rows_stay_independent_and_keep_amounts():
    """缺订单号的行**不继承上一行**, 金额也不被清空(宁可多算也不错配)。"""
    rows = [
        {
            "订单编号": "SO-REAL-1",
            "平台SKU": "SKU-A",
            "买家支付(RMB)": "100.00",
        },
        {
            "订单编号": "",
            "平台SKU": "SKU-B",
            "买家支付(RMB)": "50.00",
        },
        {
            "平台SKU": "SKU-C",
            "买家支付(RMB)": "30.00",
        },
        {
            "订单编号": "SO-REAL-2",
            "平台SKU": "SKU-D",
            "买家支付(RMB)": "70.00",
        },
    ]

    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    # 缺订单号的行没有被并进上一张订单 ⇒ 金额原样保留
    assert prepared_rows[1]["买家支付(RMB)"] == "50.00"
    assert prepared_rows[2]["买家支付(RMB)"] == "30.00"

    # 独立成行 ⇒ 不拿明细行号(也不会与相邻订单合并)
    assert identity_values[1] == {}
    assert identity_values[2] == {}

    # 真实订单仍然按自己的订单号分组(单行订单不受影响)
    assert prepared_rows[0]["买家支付(RMB)"] == "100.00"
    assert prepared_rows[3]["买家支付(RMB)"] == "70.00"


def test_missing_order_id_placeholder_is_deterministic():
    """缺订单号的行拿到**带行号**的确定性占位符 ⇒ 两行之间互不合并。"""
    rows = [
        {"平台SKU": "SKU-A", "买家支付(RMB)": "10.00"},
        {"平台SKU": "SKU-B", "买家支付(RMB)": "20.00"},
    ]

    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    assert prepared_rows[0]["买家支付(RMB)"] == "10.00"
    assert prepared_rows[1]["买家支付(RMB)"] == "20.00"
    assert identity_values == [{}, {}]

    # 同样的输入 ⇒ 同样的结果(可重放)
    again, _ = prepare_orders_rows_for_b_class(rows)
    assert again == prepared_rows

    assert MISSING_ORDER_ID_PREFIX == "__missing_order_id__:"


def test_missing_order_id_row_does_not_join_previous_order_line_counter():
    """缺订单号的行不占用上一张订单的明细行号(不产生跨单错配的 hash)。"""
    rows = [
        {"订单编号": "SO-REAL-1", "平台SKU": "SKU-A", "买家支付(RMB)": "100.00"},
        {"订单编号": "SO-REAL-1", "平台SKU": "SKU-B", "买家支付(RMB)": "100.00"},
        {"订单编号": "", "平台SKU": "SKU-C", "买家支付(RMB)": "20.00"},
    ]

    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    assert identity_values == [{}, {"_source_line_index": 2}, {}]
    assert prepared_rows[2]["买家支付(RMB)"] == "20.00"


# ── 4. 合并口径 ────────────────────────────────────────────────────────


def test_merge_prefers_existing_non_empty_derived_order_level_fields():
    """订单级字段的合并口径也走派生集合(不再依赖手写清单)。"""
    existing = {
        "买家支付(RMB)": "126.53",
        "服务费(RMB)": "2.00",
        "Shopee平台佣金(RMB)": "6.00",
        "销售数量": "3",
    }
    incoming = {
        "买家支付(RMB)": "",
        "服务费(RMB)": None,
        "Shopee平台佣金(RMB)": "",
        "销售数量": "3",
    }

    merged = merge_orders_raw_data_prefer_non_empty(existing, incoming)

    assert merged["买家支付(RMB)"] == "126.53"
    assert merged["服务费(RMB)"] == "2.00"
    assert merged["Shopee平台佣金(RMB)"] == "6.00"
    # 行级数量不参与「订单级取非空」合并
    assert merged["销售数量"] == "3"
