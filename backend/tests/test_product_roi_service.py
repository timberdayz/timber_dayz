"""阶段 1 · ROI 只读层的纯函数单测。

口径依据（上游设计稿 §2.5⑦⑨⑩⑪）：
``docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md``

这个模块**没有 ORM、没有 DB、没有 I/O**，所以 ROI 的每一条边界都能在这里钉死。
"""

from decimal import Decimal

from backend.services.product_profit_service import build_platform_profit_preview
from backend.services.product_roi_service import compute_roi_metrics


# 设计稿 §2.5⑪ 的截图那一行：P=70 / 卖家券 c=2 / 商家实收 G=68 / pre_ad_profit=34.49
NET_REVENUE = Decimal("68")
PRE_AD_PROFIT = Decimal("34.49")


def test_break_even_roi_is_net_revenue_over_pre_ad_profit():
    """用例 1：保本 ROI 公式精确值。"""
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=PRE_AD_PROFIT)
    assert metrics["break_even_roi"] == NET_REVENUE / PRE_AD_PROFIT
    assert metrics["break_even_roi"] == Decimal("1.971585966946941142360104378")


def test_break_even_roi_times_advertising_margin_rate_equals_one():
    """用例 2：break_even_roi × p == 1（p = 广告前贡献毛利率）。"""
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=PRE_AD_PROFIT)
    p = metrics["advertising_contribution_margin_rate"]
    assert p == PRE_AD_PROFIT / NET_REVENUE
    assert metrics["break_even_roi"] * p == 1


def test_suggested_roi_is_break_even_roi_times_one_point_two():
    """用例 3：suggested_roi == break_even_roi × (1 + 安全边际)。"""
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=PRE_AD_PROFIT)
    assert metrics["suggested_roi"] == metrics["break_even_roi"] * Decimal("1.20")


def test_suggested_roi_is_clamped_at_platform_ceiling_but_raw_value_is_kept():
    """用例 4：封顶到平台上限，且**未封顶原值必须保留**（运营要看真实差距）。"""
    metrics = compute_roi_metrics(
        net_revenue=NET_REVENUE,
        pre_ad_profit=Decimal("1"),
        target_roi_ceiling=Decimal("50"),
    )
    assert metrics["suggested_roi_clamped"] == Decimal("50")
    assert metrics["suggestion_note"] == "above_platform_ceiling"
    assert metrics["suggested_roi"] == NET_REVENUE / Decimal("1") * Decimal("1.20")
    assert metrics["suggested_roi"] > Decimal("50")


def test_break_even_roi_below_one_is_flagged_instead_of_being_clamped():
    """用例 5：只封顶不封底。保本 ROI < 1 是「成本算错了」的异常信号，不该被藏起来。"""
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=Decimal("80"))
    assert metrics["break_even_roi"] < 1
    assert "break_even_roi_below_one" in metrics["anomalies"]
    # 没有被抬到 1（更没有抬到 1.2）
    assert metrics["suggested_roi_clamped"] < Decimal("1.20")


def test_non_positive_cost_denominator_returns_none_with_a_reason():
    """用例 6：分母 ≤ 0 一律返回 None + 缺输入原因，绝不返回乐观值。"""
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=Decimal("0"))
    assert metrics["break_even_roi"] is None
    assert metrics["suggested_roi"] is None
    assert metrics["suggested_roi_clamped"] is None
    assert metrics["equivalent_ad_cost_per_order"] is None
    assert metrics["missing_reasons"] == ["non_positive_cost_denominator"]


def test_roi_denominator_is_merchant_net_revenue_not_goods_amount():
    """用例 7：分母口径是**商家实收**（售价 − 卖家券），不是商品金额。

    换成商品金额 P 会得到另一个数 —— 这两个数都能"算得出来"，
    但只有商家实收与平台后台同一把标尺（设计稿 §2.5⑦）。
    """
    preview = build_platform_profit_preview(
        expected_selling_price=Decimal("70"),
        competitor_price=None,
        seller_coupon_amount=Decimal("2"),
        purchase_cost=Decimal("23"),
        expected_logistics_cost=Decimal("0.38"),
        expected_storage_cost=Decimal("0"),
        expected_label_fee=Decimal("1"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.0737"),
        expected_ad_rate=Decimal("0.02"),
        return_rate=Decimal("0"),
        damage_rate=Decimal("0"),
        creator_commission_rate=None,
    )
    expected = preview["expected"]
    assert expected["net_revenue"] == Decimal("68")
    assert expected["break_even_roi"] == Decimal("68") / expected["pre_ad_profit"]
    assert expected["break_even_roi"] != Decimal("70") / expected["pre_ad_profit"]


def test_net_revenue_matches_the_platform_gmv_scale():
    """用例 8：商家实收 G = P − c = B + d（买家实付 + 平台补贴）= TikTok GMV。"""
    price = Decimal("70")
    seller_coupon = Decimal("2")
    buyer_paid = Decimal("60")
    platform_subsidy = Decimal("8")

    net_revenue = price - seller_coupon
    assert net_revenue == Decimal("68")
    assert net_revenue == buyer_paid + platform_subsidy


def test_ad_rate_and_platform_reported_roi_are_inverse():
    """用例 9：广告分成率 s ↔ 平台报告 ROI R 恒等（pre_ad_profit × s == 商家实收 ÷ R）。"""
    ad_rate = Decimal("0.15")
    metrics = compute_roi_metrics(
        net_revenue=NET_REVENUE,
        pre_ad_profit=PRE_AD_PROFIT,
        expected_ad_rate=ad_rate,
    )
    target_roi = metrics["equivalent_target_roi"]
    assert target_roi == metrics["break_even_roi"] / ad_rate
    assert NET_REVENUE / target_roi == PRE_AD_PROFIT * ad_rate


def test_equivalent_money_follows_the_two_decimal_suggested_roi():
    """等效金额必须由「运营真会填进后台的两位小数 ROI」推出。

    保本 ROI 1.97（表上显示值）→ 建议 ROI 2.36 → 单均广告费 68 ÷ 2.36 = 28.81。
    数字之间必须能互相验算，否则表上会出现「建议ROI 2.36、等效广告费 28.74」这种对不上的数。
    """
    metrics = compute_roi_metrics(net_revenue=NET_REVENUE, pre_ad_profit=PRE_AD_PROFIT)
    assert metrics["suggested_roi_clamped"] == Decimal("2.36")
    assert metrics["equivalent_ad_cost_per_order"] == Decimal("28.81")
    assert metrics["equivalent_net_profit_per_order"] == Decimal("5.68")
    # 净利率 ≈ 8.35%（设计稿 §2.5⑪ 写的 8.4%）
    assert metrics["equivalent_net_margin_rate"].quantize(Decimal("0.0001")) == Decimal(
        "0.0835"
    )


def test_zero_ad_rate_gives_no_equivalent_target_roi():
    """广告分成率没填（0）时，等效目标 ROI 算不出来 —— 但保本 ROI 照样给。"""
    metrics = compute_roi_metrics(
        net_revenue=NET_REVENUE,
        pre_ad_profit=PRE_AD_PROFIT,
        expected_ad_rate=Decimal("0"),
    )
    assert metrics["equivalent_target_roi"] is None
    assert metrics["break_even_roi"] is not None


def test_non_positive_revenue_returns_none_with_a_reason():
    metrics = compute_roi_metrics(net_revenue=Decimal("0"), pre_ad_profit=PRE_AD_PROFIT)
    assert metrics["break_even_roi"] is None
    assert metrics["missing_reasons"] == ["non_positive_revenue"]
