"""批次 9 · 平台佣金单独进分母 + 底线链与利润链同源（2026-11-19 拍板）。

新口径
------
```
分子 = (采购成本 + 头程 + 仓储 + 贴单 + 尾程) × (1 + SPU退货率 + SPU货损率)
分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率
```

本文件钉四件事：

1. **平台佣金率单独进分母** —— 以前它藏在「平台其他成本率」里，
   界面上填了**不生效**（老模块头明写"平台佣金率已包含在 other_cost_rate 内"）。
   现在「各扣各的，填的都生效」⇒ 只改平台佣金率，底线**必须**变。
2. **桶的语义 = 佣金之外、尾程之外** —— 桶只装「佣金与尾程之外」的平台侧
   按收入比例扣款；桶改大 ⇒ 底线变高。
3. **缺平台佣金率 ⇒ 报 `missing_platform_fee_rate` 且不算底线** ——
   不可省略型成本项，缺了就**不报**一个偏乐观的底线（宁可不算）。
4. **两条链同价同结果**（最强的一条）：用 `compute_cost_floor` 算出的底线作售价，
   调 `build_platform_profit_preview`（同样的费率、同样的按件成本），
   **利润率必须等于目标利润率** —— 底线链与利润链**同源**的证明。

⚠️ 口径纪律：钱分三类 —— **按件的钱进分子**（采购/头程/仓储/贴单/尾程）、
**按比例的钱进分母**（平台佣金/桶/达人佣金）、
**按风险的件损率折成钱也进分子**（退货/货损，见
`backend/tests/test_spu_loss_rate_cost_multiplier.py`）。

下面所有数字都是能手算的：分母 = 1 − 0.08 − 0.05 − 0.06 − 0.25 = **0.56**，
分子 = 12.50 × (1 + 0.04 + 0.08) = **14.00**，底线 = 14.00 / 0.56 = **25.00**。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_sku_pricing,
)
from backend.services.product_profit_service import build_platform_profit_preview

# ---------------------------------------------------------------------------
# 口径参数（全部能手算）
# ---------------------------------------------------------------------------

#: 平台佣金率（批次 9 起**单独进分母**）。
PLATFORM_FEE_RATE = Decimal("0.08")
#: 平台其他成本率（桶）：**佣金与尾程之外**的平台侧按收入比例扣款。
OTHER_COST_RATE = Decimal("0.05")
#: 达人佣金率。
CREATOR_COMMISSION_RATE = Decimal("0.06")
#: 目标利润率。
TARGET_MARGIN_RATE = Decimal("0.25")

#: SPU 两率（行业基准的**件损率**，批次 9 起按件折进分子）。
RETURN_LOSS_RATE = Decimal("0.04")
DAMAGE_RATE = Decimal("0.08")

#: 分母 = 1 − 0.08 − 0.05 − 0.06 − 0.25 = 0.56
DENOMINATOR = Decimal("0.56")
#: 按件成本合计（12.50）与折完件损率的分子（12.50 × 1.12 = 14.00）。
PER_PIECE_COST = Decimal("12.50")
NUMERATOR = Decimal("14.00")
#: 底线 = 14.00 / 0.56 = 25.00
COST_FLOOR = Decimal("25.00")


def _floor(**overrides):
    """按新口径算底线；测试里只覆盖要动的那一项。"""
    payload = {
        "purchase_cost": PER_PIECE_COST,
        "platform_fee_rate": PLATFORM_FEE_RATE,
        "other_cost_rate": OTHER_COST_RATE,
        "creator_commission_rate": CREATOR_COMMISSION_RATE,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "target_margin_rate": TARGET_MARGIN_RATE,
    }
    payload.update(overrides)
    return compute_cost_floor(**payload)


def _policy():
    return {
        "min_restock_days": 0,
        "tier_label": "日常",
        "discount_rate": Decimal("0.10"),
        "target_margin_rate": TARGET_MARGIN_RATE,
    }


def _pricing(**overrides):
    payload = {
        "purchase_cost": PER_PIECE_COST,
        "reference_selling_price": Decimal("20"),
        "creator_commission_rate": None,
        "platform_creator_commission_rate": CREATOR_COMMISSION_RATE,
        "platform_fee_rate": PLATFORM_FEE_RATE,
        "other_cost_rate": OTHER_COST_RATE,
        "spu_bound": True,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "policy": _policy(),
        "deepest_policy": _policy(),
        "min_selling_price_override": None,
        "days_since_restock": None,
        "delivery_cost": None,
        "free_shipping": False,
    }
    payload.update(overrides)
    return compute_sku_pricing(**payload)


# ---------------------------------------------------------------------------
# 1 · 平台佣金率必须单独进分母
# ---------------------------------------------------------------------------


def test_platform_fee_rate_enters_the_denominator_on_its_own():
    """只改平台佣金率 ⇒ 底线**必须**变（以前佣金藏在桶里，改它没反应）。"""
    base = _floor()
    raised = _floor(platform_fee_rate=Decimal("0.18"))

    assert base == COST_FLOOR
    assert raised != base, "平台佣金率填了不生效 = 老口径的病，必须治好"
    # 分母 = 1 − 0.18 − 0.05 − 0.06 − 0.25 = 0.46 ⇒ 14.00 / 0.46 = 30.43
    assert raised == Decimal("30.43")


def test_platform_fee_rate_is_subtracted_exactly_once():
    """平台佣金率在分母里**只扣一次**（重复扣 ⇒ 底线被抬高）。"""
    denominator = (
        Decimal("1")
        - PLATFORM_FEE_RATE
        - OTHER_COST_RATE
        - CREATOR_COMMISSION_RATE
        - TARGET_MARGIN_RATE
    )
    assert denominator == DENOMINATOR
    # 分子按件成本合计 × (1 + 退货率 + 货损率)
    numerator = PER_PIECE_COST * (Decimal("1") + RETURN_LOSS_RATE + DAMAGE_RATE)
    assert numerator == NUMERATOR
    assert _floor() == (numerator / denominator).quantize(Decimal("0.01"))


def test_platform_fee_rate_is_not_hidden_in_the_bucket():
    """平台佣金率**不是**桶的一部分 —— 两者各自进分母，互不吞并。

    口径：分母 = 1 − 平台佣金率 − 桶 − 达人佣金率 − 目标利润率，
    桶里**不含**佣金、**不含**尾程（尾程按重量段单件计价，直接进分子）。
    """
    # 只加桶（0.05 → 0.25）：分母 0.56 → 0.36，底线 14.00 / 0.36 = 38.89
    assert _floor(other_cost_rate=Decimal("0.25")) == Decimal("38.89")
    # 只加佣金（0.08 → 0.18）：分母 0.56 → 0.46，底线 14.00 / 0.46 = 30.43
    assert _floor(platform_fee_rate=Decimal("0.18")) == Decimal("30.43")
    # 两个都加：分母 0.56 → 0.26，底线 14.00 / 0.26 = 53.85
    assert _floor(
        platform_fee_rate=Decimal("0.18"), other_cost_rate=Decimal("0.25")
    ) == Decimal("53.85")


# ---------------------------------------------------------------------------
# 2 · 桶的语义 = 佣金之外、尾程之外
# ---------------------------------------------------------------------------


def test_bucket_growing_raises_the_cost_floor():
    """桶改大 ⇒ 底线变高（桶是按收入比例的扣款，必须真的扣）。"""
    base = _floor()
    bigger = _floor(other_cost_rate=Decimal("0.15"))

    assert bigger > base
    # 分母 0.56 → 0.46 ⇒ 14.00 / 0.46 = 30.43
    assert bigger == Decimal("30.43")


def test_bucket_only_affects_the_denominator():
    """桶只动分母，不动分子（按件成本与件损乘数不受桶影响）。"""
    with_bucket = _floor(other_cost_rate=Decimal("0.25"))
    without_bucket = _floor(other_cost_rate=Decimal("0"))
    # 分子两边都是 14.00 ⇒ 底线之比 = 分母之比的倒数
    assert without_bucket == (NUMERATOR / Decimal("0.61")).quantize(Decimal("0.01"))
    assert with_bucket == (NUMERATOR / Decimal("0.36")).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# 3 · 缺平台佣金率 ⇒ 报缺且不算底线
# ---------------------------------------------------------------------------


def test_missing_platform_fee_rate_blocks_the_cost_floor():
    """缺平台佣金率 ⇒ `missing_platform_fee_rate`，且**不算底线**。

    ⚠️ 不可省略型成本项：缺了就**不报**一个偏乐观的底线（宁可不算）。
    最低售价此时只能来自纪律线（``discount_guard``），来源必须如实标出来。
    """
    out = _pricing(platform_fee_rate=None)

    assert "missing_platform_fee_rate" in out["min_selling_price_missing_reasons"]
    assert out["min_selling_price_source"] == "discount_guard"
    # 纪律线 = 参考售价 20 × (1 − 0.10) = 18.00（成本线算不出来，只能用它）
    assert out["min_selling_price"] == pytest.approx(18.00, abs=0.01)
    # 有佣金时不得报这条缺料
    ok = _pricing()
    assert "missing_platform_fee_rate" not in ok["min_selling_price_missing_reasons"]
    assert ok["min_selling_price_source"] == "cost_floor"
    assert ok["min_selling_price"] == pytest.approx(25.00, abs=0.01)
    assert out["min_selling_price"] != ok["min_selling_price"]


def test_missing_bucket_blocks_the_cost_floor():
    """缺桶同样不算底线（沿用 `missing_platform_cost_rate`）。"""
    out = _pricing(other_cost_rate=None)
    assert "missing_platform_cost_rate" in out["min_selling_price_missing_reasons"]
    assert out["min_selling_price_source"] == "discount_guard"


# ---------------------------------------------------------------------------
# 4 · 两条链同价同结果（最强的一条守护）
# ---------------------------------------------------------------------------


def _preview_at_floor(*, purchase_cost, per_piece_extras, floor):
    """用**底线**作售价调利润试算链（同样的费率、同样的按件成本）。

    ⚠️ 按件成本里没有的项一律显式传 **0**（不是 None）：
    利润链的「按件成本合计」只要有一项是 None ⇒ 整条链算不出来。
    底线链那边这些项缺省就是 0 ⇒ 两边必须是同一个数。
    """
    return build_platform_profit_preview(
        expected_selling_price=floor,
        competitor_price=None,
        purchase_cost=purchase_cost,
        expected_logistics_cost=per_piece_extras.get("logistics_cost", Decimal("0")),
        expected_storage_cost=per_piece_extras.get("storage_cost", Decimal("0")),
        expected_label_fee=per_piece_extras.get("label_fee", Decimal("0")),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        expected_ad_rate=Decimal("0"),
        target_roi=None,
        return_rate=RETURN_LOSS_RATE,
        damage_rate=DAMAGE_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        delivery_cost=per_piece_extras.get("delivery_cost", Decimal("0")),
    )


#: 三个场景的按件成本合计都是 12.50 ⇒ 底线都是 25.00，
#: 但**按件成本的构成**不同（这是三场景的差别所在）。
SCENARIOS = [
    pytest.param(
        Decimal("12.50"),
        {},
        id="no_free_shipping_no_delivery",
    ),
    pytest.param(
        Decimal("8.00"),
        {"delivery_cost": Decimal("4.50")},
        id="free_shipping_with_delivery",
    ),
    pytest.param(
        Decimal("7.00"),
        {
            "logistics_cost": Decimal("3.00"),
            "storage_cost": Decimal("1.50"),
            "label_fee": Decimal("1.00"),
        },
        id="with_fulfillment_costs",
    ),
]


@pytest.mark.parametrize("purchase_cost,extras", SCENARIOS)
def test_cost_floor_and_profit_chain_agree_on_the_same_price(purchase_cost, extras):
    """**底线链与利润链同源**：在底线上算利润，利润率必须 = 目标利润率。

    这是本批最强的一条守护：底线说"卖到这个价利润率恰好是目标利润率"，
    利润链必须给出**同一个数**。两条链口径一分叉（以前利润链不扣桶、
    两率按收入比例扣），差出来的是 26.78 个百分点 ——
    护栏拿着偏松的底线放行本该拦住的品。

    ⚠️ 容差 1e-6：这里的数字被刻意选成**每一步都恰好到分**
    （底线 25.00 是整元，各费率都是两位小数），
    所以量化不会引入误差 —— 容差收紧到 1e-6 也不会被"四舍五入"掩盖。
    """
    floor = _floor(
        purchase_cost=purchase_cost,
        delivery_cost=extras.get("delivery_cost"),
        logistics_cost=extras.get("logistics_cost"),
        storage_cost=extras.get("storage_cost"),
        label_fee=extras.get("label_fee"),
    )
    assert floor == COST_FLOOR

    preview = _preview_at_floor(
        purchase_cost=purchase_cost, per_piece_extras=extras, floor=floor
    )
    expected = preview["expected"]

    # 利润链必须算得出来（缺桶 ⇒ 整条链空白）
    assert expected["completeness"] == "complete"
    assert expected["profit"] is not None
    # 利润率 = 目标利润率
    assert float(expected["margin_rate"]) == pytest.approx(0.25, abs=1e-6)
    # 目标利润率 25% × 底线 25.00 = 6.25
    assert expected["profit"] == Decimal("6.25")
    assert expected["pre_ad_profit"] == Decimal("6.25")
    # 利润链**必须扣桶**（批次 9：以前利润链不扣桶 ⇒ 两条链恒差一个桶）
    assert expected["other_cost"] == Decimal("1.25")
    # 平台佣金率也**必须**进利润链
    assert expected["platform_fee"] == Decimal("2.00")
    # 两率按**件成本**折（不是按收入比例）
    assert expected["return_loss"] == Decimal("0.50")
    assert expected["damage_loss"] == Decimal("1.00")


@pytest.mark.parametrize("purchase_cost,extras", SCENARIOS)
def test_profit_chain_without_the_bucket_would_overstate_profit(purchase_cost, extras):
    """反证：利润链**不扣桶**的话，同一个价上的利润率会明显高于目标利润率。

    这条是为了让"扣桶"这件事有一个**可观测的失败信号**：
    万一哪天有人把桶从利润链里删掉，第一条守护会红，这条也会红。
    """
    floor = COST_FLOOR
    with_bucket = _preview_at_floor(
        purchase_cost=purchase_cost, per_piece_extras=extras, floor=floor
    )["expected"]
    without_bucket = build_platform_profit_preview(
        expected_selling_price=floor,
        competitor_price=None,
        purchase_cost=purchase_cost,
        expected_logistics_cost=extras.get("logistics_cost", Decimal("0")),
        expected_storage_cost=extras.get("storage_cost", Decimal("0")),
        expected_label_fee=extras.get("label_fee", Decimal("0")),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=PLATFORM_FEE_RATE,
        # 桶传 0 ⇒ 相当于"这条链不扣桶"
        other_cost_rate=Decimal("0"),
        expected_ad_rate=Decimal("0"),
        target_roi=None,
        return_rate=RETURN_LOSS_RATE,
        damage_rate=DAMAGE_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        delivery_cost=extras.get("delivery_cost", Decimal("0")),
    )["expected"]

    assert float(with_bucket["margin_rate"]) == pytest.approx(0.25, abs=1e-6)
    # 不扣桶 ⇒ 利润率虚高 5 个百分点（桶 5%）
    assert float(without_bucket["margin_rate"]) == pytest.approx(0.30, abs=1e-6)
    assert without_bucket["profit"] > with_bucket["profit"]
