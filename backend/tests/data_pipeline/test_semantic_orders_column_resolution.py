"""orders 域列名 ↔ 标准字段的解析契约 —— 2026-11-08。

背景
----
源表的金额列**成对出现**: ``X``(原币) 与 ``X(RMB)``(人民币)。
2026-11 开发库实测(shopee monthly 29629 行)::

    买家支付:     原币均值 240.11 / (RMB) 均值 72.03(非零行 27672, 相等仅 391)
    利润:         原币均值  27.98 / (RMB) 均值 11.06
    仓库操作费:   原币均值  11.56 / (RMB) 均值  4.99
    订单原始金额: 原币均值 269.53 / (RMB) 均值 78.72
    卖家支付运费: 原币均值 -40.36 / (RMB) 均值 -14.13
    广告成本:     原币均值  20.51 / (RMB) 均值   6.71

⇒ 裸名列与 ``(RMB)`` 列是**两个不同的业务事实**, 差 2~3 倍。

本文件锁死的不变量:

1. 真实源表列名 → 标准字段的映射**唯一**且**正确**(逐字, 不做币种归一化);
2. **裸名列(原币)不接任何标准字段** —— 接了就是混币种;
3. 平台间同业务不同列名 ⇒ 必须走 ``platform_code`` 维度, 不许抢张;
4. 归一化后**不得**把 ``X`` 与 ``X(RMB)`` 压成同一个 key。

⚠ 第 4 条是硬红线: ``normalize_alias("X(RMB)") == normalize_alias("X")``
⇒ 归一化匹配会在两个**不同业务事实**之间随机取一个 ⇒ orders 域**必须逐字匹配**。
"""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from backend.services.semantic_field_registry import (
    DOMAIN_CLOSED_ALIAS_DOMAINS,
    DOMAIN_PLATFORM_SEMANTIC_ALIASES,
    ORDER_PLATFORM_ALIASES,
    ORDER_SEMANTIC_ALIASES,
    ORDER_STANDARD_FIELDS,
    SEMANTIC_FIELD_DEFINITIONS,
    normalize_semantic_alias,
)


#: 真实源表列名 → 标准字段(2026-11 开发库实测的表头清单)
REAL_HEADER_MAPPING: Tuple[Tuple[str, str], ...] = (
    # 身份与维度
    ("订单编号", "order_id"),
    ("订单号", "order_id"),
    ("订单状态", "order_status"),
    ("下单时间", "order_date"),
    ("产品ID", "product_id"),
    ("商品ID", "product_id"),
    ("商品名称", "product_name"),
    ("商品SKU", "product_sku"),
    ("平台SKU", "platform_sku"),
    ("SKU ID", "sku_id"),
    # 量类
    ("销售数量", "sales_volume"),
    ("买家数", "buyer_count"),
    # 金额(人民币口径)
    ("利润(RMB)", "profit"),
    ("采购成本(RMB)", "purchase_amount"),
    ("退款金额(RMB)", "refund_amount"),
    ("预估回款金额(RMB)", "estimated_settlement_amount"),
    ("已结算金额(RMB)", "settled_amount"),
    ("仓库操作费(RMB)", "warehouse_operation_fee"),
    ("广告成本(RMB)", "promotion_fee"),
    # 平台分别列名
    ("买家支付(RMB)", "paid_amount"),
    ("买家实付金额(RMB)", "paid_amount"),
    ("卖家支付运费(RMB)", "shipping_fee"),
    ("商家运费(RMB)", "shipping_fee"),
    ("Shopee平台佣金(RMB)", "platform_commission"),
    ("TikTok 平台佣金(RMB)", "platform_commission"),
    ("Shopee voucher(RMB)", "platform_voucher"),
    ("卖家voucher(RMB)", "seller_voucher"),
    ("服务费(RMB)", "platform_service_fee"),
    ("订单原始金额(RMB)", "order_original_amount"),
    ("产品原价(RMB)", "order_original_amount"),
)


#: 裸名列(原币)—— **不许**接任何标准字段。
BARE_ORIGINAL_CURRENCY_COLUMNS: Tuple[str, ...] = (
    "利润",
    "采购成本",
    "采购金额",
    "退款金额",
    "预估回款金额",
    "已结算金额",
    "仓库操作费",
    "广告成本",
    "运费",
    "买家支付",
    "买家实付金额",
    "卖家支付运费",
    "商家运费",
    "服务费",
    "卖家voucher",
    "Shopee voucher",
    "订单原始金额",
    "产品折后价格",
)


def _generic_owner() -> Dict[str, str]:
    owner: Dict[str, str] = {}
    for standard_field, aliases in ORDER_SEMANTIC_ALIASES.items():
        for alias in aliases:
            owner[alias] = standard_field
    return owner


def _platform_owner() -> Dict[str, Dict[str, str]]:
    owner: Dict[str, Dict[str, str]] = {}
    for platform_code, per_platform in ORDER_PLATFORM_ALIASES.items():
        bucket: Dict[str, str] = {}
        for standard_field, aliases in per_platform.items():
            for alias in aliases:
                bucket[alias] = standard_field
        owner[platform_code] = bucket
    return owner


@pytest.mark.parametrize(("raw_alias", "standard_field"), REAL_HEADER_MAPPING)
def test_real_header_maps_to_expected_standard_field(raw_alias, standard_field):
    """真实源表列名必须解析到正确的标准字段。"""
    generic = _generic_owner()
    platform = _platform_owner()

    resolved = generic.get(raw_alias)
    for bucket in platform.values():
        resolved = resolved or bucket.get(raw_alias)

    assert (
        resolved == standard_field
    ), f"真实列名 {raw_alias!r} 解析到 {resolved!r}, 期望 {standard_field!r}"


@pytest.mark.parametrize("raw_alias", BARE_ORIGINAL_CURRENCY_COLUMNS)
def test_bare_original_currency_column_is_not_mapped(raw_alias):
    """裸名列(原币)不许接任何标准字段 —— 接了就是混币种。"""
    generic = _generic_owner()
    for bucket in _platform_owner().values():
        assert raw_alias not in bucket, f"{raw_alias!r} 不许出现在平台别名里"
    assert raw_alias not in generic, f"裸名列 {raw_alias!r} 不许接任何标准字段"


def test_normalization_must_not_collapse_currency_variants():
    """⚠ 硬红线: 归一化会把 ``X`` 与 ``X(RMB)`` 压成同一个 key。

    ⇒ orders 域**不许**用归一化匹配, 只许逐字。
    """
    for bare in ("利润", "仓库操作费", "买家支付"):
        assert normalize_semantic_alias(bare) == normalize_semantic_alias(
            "%s(RMB)" % bare
        ), f"{bare} 与 {bare}(RMB) 归一化后相同 ⇒ 归一化匹配会混币种"


def test_platform_scoped_columns_are_not_shared_between_platforms():
    """平台间同业务不同列名 ⇒ 各自只认自己的列名。"""
    platform = _platform_owner()
    assert platform["shopee"]["买家支付(RMB)"] == "paid_amount"
    assert platform["tiktok"]["买家实付金额(RMB)"] == "paid_amount"
    assert "买家支付(RMB)" not in platform["tiktok"]
    assert "买家实付金额(RMB)" not in platform["shopee"]

    assert platform["shopee"]["Shopee平台佣金(RMB)"] == "platform_commission"
    assert platform["tiktok"]["TikTok 平台佣金(RMB)"] == "platform_commission"
    assert "Shopee平台佣金(RMB)" not in platform["tiktok"]
    assert "TikTok 平台佣金(RMB)" not in platform["shopee"]


def test_one_column_belongs_to_exactly_one_standard_field():
    """「一列只认一个标准字段」—— 否则 PG 侧解析结果不确定。"""
    owners: Dict[str, set] = {}
    for standard_field, aliases in ORDER_SEMANTIC_ALIASES.items():
        for alias in aliases:
            owners.setdefault(alias, set()).add(standard_field)
    for platform_code, per_platform in ORDER_PLATFORM_ALIASES.items():
        for standard_field, aliases in per_platform.items():
            for alias in aliases:
                owners.setdefault(alias, set()).add(
                    "%s/%s" % (platform_code, standard_field)
                )

    conflicts = {
        alias: sorted(fields) for alias, fields in owners.items() if len(fields) > 1
    }
    assert not conflicts, f"同一个列名被多个标准字段认领: {conflicts}"


def test_orders_domain_is_closed_for_global_bare_aliases():
    """orders 域是**封闭域** —— 不从全局别名表补裸名。

    原因: orders 域的裸名指的是**原币列**, 补进来 = 混币种。
    """
    assert "orders" in DOMAIN_CLOSED_ALIAS_DOMAINS
    assert "orders" in DOMAIN_PLATFORM_SEMANTIC_ALIASES


def test_every_standard_field_has_a_definition():
    """orders 域的标准字段清单从字典派生 ⇒ 每个字段都得有定义。"""
    missing = [
        key for key in ORDER_STANDARD_FIELDS if key not in SEMANTIC_FIELD_DEFINITIONS
    ]
    assert not missing, f"orders 标准字段缺定义: {missing}"


def test_retired_sales_amount_is_not_in_standard_fields():
    """``sales_amount`` 已废止 —— 源表没有对应列, 以前恒 0。"""
    from backend.services.semantic_field_registry import ORDER_RETIRED_FIELDS

    assert "sales_amount" in ORDER_RETIRED_FIELDS
    assert "sales_amount" not in ORDER_STANDARD_FIELDS
