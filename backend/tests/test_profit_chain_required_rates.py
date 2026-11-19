"""利润链的**必填平台费率**（批次 9）守护测试。

背景
----
批次 9 把「平台其他成本率」（桶）正式拉进利润链的扣项：

    广告前利润 = 商家实收 − (采购 + 头程 + 仓储 + 贴单 + 尾程 + 平台佣金 + 达人佣金 + 桶 + 件损)

⇒ 桶与平台佣金率一样，是**必填成本项**：
   缺任何一个 ⇒ 整条利润链算不出来（**不是按 0 计**）。

⚠️ 为什么这条要单独钉：批次 9 之前，利润链**压根不扣桶**
⇒ 桶为 NULL 不会让利润链留白。批次 9 把桶加进扣项之后，
**新增了一条「桶没配 ⇒ 利润空白」的失败路径**，而这条路径最初**没有任何原因码指向它**：

* 运营看到的是一片空白（profit = None），
* 系统给的原因是「完整预计利润口径」（一句没法定位的兜底话），
* 于是运营根本不知道该去「定价设置」里补**哪个**费率。

本文件钉三件事：

1. 桶为 NULL ⇒ 利润链留白 **且**报 ``missing_platform_cost_rate``（不静默按 0 计）。
2. 平台佣金率为 NULL ⇒ 报 ``missing_platform_fee_rate``（同一个失败模式，一并钉住）。
3. 原因码与**底线链**用同一套词（``product_pricing_service`` 里就是这两个键）——
   同一个「平台侧费率没配」，两条链不能一个叫这个、一个叫那个。

口径纪律
--------
* **缺输入宁可不算，不可乐观**：费率缺失 ⇒ 利润留白，绝不按 0 计
  （按 0 计等于凭空多一笔利润 ⇒ 看着很美，实际在亏）。
* **0 是有效值**：明确配 0 ⇒ 不是缺料（桶就是 0% 扣款，不是「没配」）。
"""

from decimal import Decimal

import pytest

from backend.services.product_profit_service import build_platform_profit_preview

D = Decimal


def _preview(**overrides):
    """利润链的公共入参。

    ⚠️ 桶与平台佣金率都**显式给值**（默认 0），
    这样被测的那一项才是唯一变量 —— 其余用例要改的是它们自己的口径。
    """
    payload = dict(
        expected_selling_price=D("100"),
        competitor_price=None,
        purchase_cost=D("30"),
        expected_logistics_cost=D("8"),
        expected_storage_cost=D("2"),
        expected_label_fee=None,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=D("0.08"),
        other_cost_rate=D("0"),
        expected_ad_rate=D("0.10"),
        return_rate=D("0.03"),
        damage_rate=D("0.02"),
        creator_commission_rate=D("0.06"),
        delivery_cost=D("0"),
    )
    payload.update(overrides)
    return build_platform_profit_preview(**payload)


# ---------------------------------------------------------------------------
# 1 · 桶（平台其他成本率）是必填项
# ---------------------------------------------------------------------------


def test_missing_bucket_blanks_the_chain_and_names_the_bucket():
    """桶为 NULL ⇒ 利润链留白 **且**点名是桶没配。

    ⚠️ 两件事必须同时成立：
    * 留白（不是按 0 计）—— 按 0 计等于凭空多一笔利润；
    * 点名（不是「资料不全」）—— 运营要知道去补**哪个**费率。
    """
    result = _preview(other_cost_rate=None)

    assert result["expected"]["profit"] is None
    assert result["expected"]["other_cost"] is None
    reasons = result["expected"]["platform_rate_missing_reasons"]
    assert "missing_platform_cost_rate" in reasons


def test_missing_platform_fee_rate_blanks_the_chain_and_names_the_commission():
    """平台佣金率为 NULL ⇒ 同样留白 **且**点名是佣金率没配。

    ⚠️ 这条与桶是**同一个失败模式**（必填平台费率缺失），
    批次 9 之前同样没有任何原因码指向它 —— 一并钉住。
    """
    result = _preview(platform_fee_rate=None)

    assert result["expected"]["profit"] is None
    assert result["expected"]["platform_fee"] is None
    reasons = result["expected"]["platform_rate_missing_reasons"]
    assert "missing_platform_fee_rate" in reasons


def test_both_rates_missing_reports_both_reasons():
    """两个都没配 ⇒ 两个原因都要报（不能只报一个，否则运营补完一个还是算不出来）。"""
    result = _preview(platform_fee_rate=None, other_cost_rate=None)

    reasons = result["expected"]["platform_rate_missing_reasons"]
    assert "missing_platform_fee_rate" in reasons
    assert "missing_platform_cost_rate" in reasons


# ---------------------------------------------------------------------------
# 2 · 0 是有效值，不是缺料
# ---------------------------------------------------------------------------


def test_zero_rates_are_valid_values_not_missing_inputs():
    """费率明确配 0 ⇒ 不是缺料。

    ⚠️ 「0% 扣款」和「没配」是两回事：
    前者是业务事实（这个平台确实不扣这笔），
    后者是数据缺失。混为一谈会让运营去补一个**根本不需要补**的费率。
    """
    result = _preview(platform_fee_rate=D("0"), other_cost_rate=D("0"))

    assert result["expected"]["platform_rate_missing_reasons"] == []
    assert result["expected"]["profit"] is not None


def test_bucket_is_deducted_from_the_chain_when_present():
    """桶必须在链上真扣（不是只报原因不扣钱）。

    ⚠️ 「报缺料原因」与「真扣钱」是两件事：
    桶报出来了却没扣 ⇒ 利润虚高 ⇒ 比不报还坏。

    ⚠️ 利润的差额**不等于**桶的金额：广告费是按「广告前利润 × 分成率」算的，
    广告前利润少了桶 ⇒ 广告费也跟着少 ⇒ 最终利润的差额 = 桶 × (1 − 分成率)。
    这里 100 × 10% = 10.00 ⇒ 利润差 10.00 × 0.9 = **9.00**（分成率 10%）。
    """
    without = _preview(other_cost_rate=D("0"))["expected"]
    with_bucket = _preview(other_cost_rate=D("0.10"))["expected"]

    # 桶 = 100 × 10% = 10.00
    assert with_bucket["other_cost"] == D("10.00")
    # 广告前利润正好差一个桶（10.00）
    assert without["pre_ad_profit"] - with_bucket["pre_ad_profit"] == D("10.00")
    # 最终利润差 = 桶 × (1 − 广告分成率) = 10.00 × 0.9 = 9.00
    assert without["profit"] - with_bucket["profit"] == D("9.00")


# ---------------------------------------------------------------------------
# 3 · 两条链用同一套原因码
# ---------------------------------------------------------------------------


def test_reason_codes_match_the_cost_floor_chain_vocabulary():
    """利润链的原因码必须与**底线链**一致。

    ⚠️ 同一种缺失（平台侧费率没配），底线链叫 ``missing_platform_cost_rate``，
    利润链不能另起一个名 —— 两套词会让运营在两个界面上看到两件事。
    """
    from backend.services.product_pricing_service import compute_sku_pricing

    floor = compute_sku_pricing(
        purchase_cost=D("30"),
        reference_selling_price=None,
        creator_commission_rate=D("0.06"),
        platform_creator_commission_rate=None,
        platform_fee_rate=None,
        other_cost_rate=None,
        spu_bound=True,
        spu_return_loss_rate=D("0.03"),
        spu_damage_rate=D("0.02"),
        policy={
            "target_margin_rate": D("0.25"),
            "discount_rate": D("0.1"),
            "tier_label": "普通商品",
            "min_restock_days": 60,
        },
        deepest_policy=None,
        min_selling_price_override=None,
        days_since_restock=10,
    )

    profit_reasons = _preview(platform_fee_rate=None, other_cost_rate=None)["expected"][
        "platform_rate_missing_reasons"
    ]

    floor_reasons = floor["min_selling_price_missing_reasons"]
    assert "missing_platform_fee_rate" in floor_reasons
    assert "missing_platform_cost_rate" in floor_reasons
    # 两边点名的是**同一批**缺失
    assert set(profit_reasons) <= set(floor_reasons)


# ---------------------------------------------------------------------------
# 4 · 入参纪律：桶不许有「忘了传就按 0」的默认值
# ---------------------------------------------------------------------------


def test_other_cost_rate_parameter_has_no_default():
    """桶不许有默认值 —— 忘了传就必须报错，不能悄悄按 0 计。

    ⚠️ 默认值 ``None`` 会让「调用方忘了传」和「调用方明确说不扣」变成同一件事：
    调用方忘传 ⇒ 链留白 ⇒ 运营以为是费率问题，去补费率；
    而真因是**代码漏传**。宁可 TypeError 逼调用方当场发现。
    """
    with pytest.raises(TypeError):
        build_platform_profit_preview(
            expected_selling_price=D("100"),
            competitor_price=None,
            purchase_cost=D("30"),
            expected_logistics_cost=D("8"),
            expected_storage_cost=D("2"),
            actual_logistics_cost=None,
            actual_storage_cost=None,
            platform_fee_rate=D("0.08"),
            expected_ad_rate=D("0.10"),
            return_rate=D("0.03"),
            damage_rate=D("0.02"),
            delivery_cost=D("0"),
        )
