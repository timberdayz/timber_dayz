"""口径（caliber）对齐契约 —— 2026-11-08。

背景: shopee / tiktok 商品报表对同一个指标给**多套统计口径**
(「已下单」与「已付款」)。实测两套口径的销售额平均差 5.15%、最大差 175.89
⇒ 它们是**不同的业务事实**, 绝不能归一化成同一个值。

本文件锁死三条原则:
1. 两套口径必须落到**不同**的标准字段;
2. 平台改口径词(旧词)必须仍然能命中;
3. 没有实测支撑的旧词**不猜**(落 unknown)。
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def infer():
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    return infer_semantic_key_for_domain


# ---------------------------------------------------------------------------
# 1. 两套口径落到不同标准字段
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("已付款订单", "order_count"),
        ("已下订单", "order_count_placed"),
        ("销售额（已付款订单）", "sales_amount"),
        ("销售额（已下订单）", "sales_amount_placed"),
        ("件数（已付款订单）", "sales_volume"),
        ("件数（已下订单）", "sales_volume_placed"),
        ("转化率（已付款订单）", "conversion_rate"),
        ("转化率（已下订单）", "conversion_rate_placed"),
        ("订单转化率（已付款订单）", "order_conversion_rate"),
        ("订单转化率（已下订单）", "order_conversion_rate_placed"),
        ("买家数（已付款订单）", "buyer_count"),
        ("买家数（已下订单）", "buyer_count_placed"),
        ("每笔订单销售额（已付款订单）", "aov"),
        ("每笔订单销售额（已下订单）", "aov_placed"),
    ],
)
def test_calibers_map_to_distinct_standard_fields(infer, header, expected):
    """已付款口径与已下单口径必须落在**不同**的标准字段上。"""
    assert infer("products", header) == expected


def test_caliber_variants_never_share_one_standard_field():
    """同一个指标的两种口径不得共用一个标准字段(否则口径会被静默混掉)。"""
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    pairs = [
        ("已付款订单", "已下订单"),
        ("销售额（已付款订单）", "销售额（已下订单）"),
        ("件数（已付款订单）", "件数（已下订单）"),
        ("转化率（已付款订单）", "转化率（已下订单）"),
    ]
    for paid_header, placed_header in pairs:
        paid = infer_semantic_key_for_domain("products", paid_header)
        placed = infer_semantic_key_for_domain("products", placed_header)
        assert paid and placed
        assert paid != placed, f"{paid_header} 与 {placed_header} 落到了同一个字段 {paid}"


# ---------------------------------------------------------------------------
# 2. 口径沿革: 平台改词后仍然能命中
# ---------------------------------------------------------------------------


def test_legacy_caliber_word_still_resolves(infer):
    """「已确定订单」是「已下订单」的旧叫法 ⇒ 仍然落到 placed 口径。"""
    assert infer("products", "销售额（已确定订单）") == "sales_amount_placed"
    assert infer("products", "件数（已确定订单）") == "sales_volume_placed"


def test_legacy_word_is_not_guessed_without_evidence(infer):
    """「已确认订单」在真实数据里没有任何数值 ⇒ 无从判断口径 ⇒ 不猜。"""
    assert infer("products", "销售额（已确认订单）") is None


def test_caliber_history_is_platform_scoped():
    """未登记沿革的平台不被折算。"""
    from backend.services.semantic_field_registry import (
        apply_caliber_history,
        normalize_semantic_alias,
    )

    raw = "销售额（已确定订单）"
    assert apply_caliber_history(normalize_semantic_alias(raw), "shopee") == "销售额(已下单)"
    assert apply_caliber_history(normalize_semantic_alias(raw), "tiktok") == (
        normalize_semantic_alias(raw)
    )


# ---------------------------------------------------------------------------
# 3. 归一化: 币种后缀 / Excel 序号后缀 / 全角标点
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("销售额（已付款订单） (SGD)", "sales_amount"),
        ("销售额（已付款订单） (USD)", "sales_amount"),
        ("商品曝光次数.1", "unique_impressions"),
        ("GMV.2", "gmv"),
        ("Current Item Status", "item_status"),
        ("商品编号", "product_id"),
    ],
)
def test_normalized_headers_resolve(infer, header, expected):
    """币种后缀 / Excel 重名序号 / 全角标点 都要能命中。"""
    assert infer("products", header) == expected


# ---------------------------------------------------------------------------
# 4. 域隔离: products 的别名不得污染其它域
# ---------------------------------------------------------------------------


def test_products_aliases_do_not_leak_into_orders(infer):
    """products 域登记的别名不得让 orders 域凭空认出同一列。"""
    assert infer("orders", "销售额（已付款订单）") is None
    assert infer("analytics", "销售额（已付款订单）") is None


# ---------------------------------------------------------------------------
# 5. 字典自身的完整性
# ---------------------------------------------------------------------------


def test_caliber_metadata_is_consistent():
    """带 caliber 的字段必须落在允许的取值上; 口径变体必须有配对主字段。"""
    from backend.services.semantic_field_registry import (
        CALIBER_PAID,
        CALIBER_PLACED,
        SEMANTIC_FIELD_DEFINITIONS,
    )

    allowed = {CALIBER_PAID, CALIBER_PLACED}
    for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
        caliber = meta.get("caliber")
        if caliber is not None:
            assert caliber in allowed, f"{key} 的 caliber 取值非法: {caliber}"

    # 口径变体字段与主字段必须成对存在
    for base in (
        "sales_amount",
        "sales_volume",
        "order_count",
        "conversion_rate",
        "order_conversion_rate",
        "buyer_count",
        "aov",
    ):
        placed = f"{base}_placed"
        assert placed in SEMANTIC_FIELD_DEFINITIONS, f"缺口径变体: {placed}"
        assert SEMANTIC_FIELD_DEFINITIONS[placed].get("caliber") == CALIBER_PLACED
        assert SEMANTIC_FIELD_DEFINITIONS[base].get("caliber") == CALIBER_PAID


def test_every_standard_field_has_a_description():
    """新增标准字段必须补前端说明文案(否则下拉框会显示空标签)。"""
    from backend.services.semantic_field_registry import (
        SEMANTIC_FIELD_DEFINITIONS,
        SEMANTIC_FIELD_DESCRIPTIONS,
    )

    missing = [
        key for key in SEMANTIC_FIELD_DEFINITIONS if key not in SEMANTIC_FIELD_DESCRIPTIONS
    ]
    assert not missing, f"缺说明文案的标准字段: {missing}"
