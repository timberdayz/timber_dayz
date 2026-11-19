"""批次 9 · SPU 退货率/货损率按件折进成本（2026-11-19 拍板）。

口径变更
--------
旧口径（错）：SPU 退货率 / 货损率当**收入比例**扣（分母减 R/D）
⇒ 说的是"每卖 100 块收入，有几块收不回来"。

新口径（对）：这两个率是**行业基准的件损率**
（"这个款在行业主流数据下，发 100 件里退几件、坏几件"）
⇒ 付了 100 件货的钱只卖出 (1 − R − D) 件
⇒ 每卖 1 件要多摊 **(1 + R + D)** 倍的按件成本 ⇒ **乘进分子**。

```
分子 = (采购 + 头程 + 仓储 + 贴单 + 尾程) × (1 + SPU退货率 + SPU货损率)
分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率
```

本文件钉六件事：

1. 分子**必须**乘 `(1 + R + D)`（写死具体数字，不只是"变大了"）。
2. 分母**不得**再扣这两个率（底线变化**只**来自分子的乘数）。
3. 两率任一为空 ⇒ 报 `missing_spu_rates` 且**不算底线**（不放宽）。
4. 尾程**直接进分子**；旧的「尾程占收入比」与「成对生效」已退役。
5. 履约按件成本（头程/仓储/贴单）**进分子**。
6. `compute_cost_floor` **不再接受** `delivery_cost_rate`（退役钉死）。

⚠️ 下面所有数字都能手算：分母 = 1 − 0.08 − 0.05 − 0.06 − 0.20 = **0.61**。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_sku_pricing,
)

# ---------------------------------------------------------------------------
# 口径参数（全部能手算）
# ---------------------------------------------------------------------------

PLATFORM_FEE_RATE = Decimal("0.08")
OTHER_COST_RATE = Decimal("0.05")
CREATOR_COMMISSION_RATE = Decimal("0.06")
TARGET_MARGIN_RATE = Decimal("0.20")

#: 分母 = 1 − 0.08 − 0.05 − 0.06 − 0.20 = 0.61
DENOMINATOR = Decimal("0.61")

#: SPU 两率（行业基准的件损率）。
RETURN_LOSS_RATE = Decimal("0.15")
DAMAGE_RATE = Decimal("0.10")
#: 件损乘数 = 1 + 0.15 + 0.10 = 1.25
LOSS_MULTIPLIER = Decimal("1.25")

#: 采购成本 100 ⇒ 分子 100 × 1.25 = 125 ⇒ 底线 125 / 0.61 = 204.92
PURCHASE_COST = Decimal("100")
NUMERATOR = Decimal("125")
COST_FLOOR = Decimal("204.92")
#: 两率为 0 ⇒ 分子 100 ⇒ 底线 100 / 0.61 = 163.93
COST_FLOOR_WITHOUT_LOSS = Decimal("163.93")


def _floor(**overrides):
    payload = {
        "purchase_cost": PURCHASE_COST,
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
        "purchase_cost": PURCHASE_COST,
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
# 1 · 分子必须乘 (1 + R + D)
# ---------------------------------------------------------------------------


def test_numerator_is_multiplied_by_the_loss_rates():
    """分子 = 按件成本合计 × (1 + 退货率 + 货损率)（写死数字）。"""
    assert _floor() == COST_FLOOR
    # 分子 100 × 1.25 = 125，分母 0.61 ⇒ 125 / 0.61 = 204.9180… ⇒ 204.92
    assert _floor() == (NUMERATOR / DENOMINATOR).quantize(Decimal("0.01"))


def test_loss_multiplier_is_not_applied_to_the_denominator():
    """旧口径（分母扣 R/D）算出来的数**必须不是**底线。

    旧口径：分母 = 0.61 − 0.25 = 0.36 ⇒ 125 / 0.36 = 347.22
    —— 这就是批次 9 要治的病：**收入比例扣**把底线抬成了一个说错话的数。
    """
    old_caliber = (NUMERATOR / (DENOMINATOR - RETURN_LOSS_RATE - DAMAGE_RATE)).quantize(
        Decimal("0.01")
    )
    assert old_caliber == Decimal("347.22")
    assert _floor() != old_caliber


# ---------------------------------------------------------------------------
# 2 · 分母不得再扣这两个率
# ---------------------------------------------------------------------------


def test_denominator_does_not_subtract_the_loss_rates():
    """底线变化**只**来自分子的乘数 —— 分母必须一动不动。"""
    without_loss = _floor(
        spu_return_loss_rate=Decimal("0"), spu_damage_rate=Decimal("0")
    )
    with_loss = _floor()

    # 两率为 0 ⇒ 分子就是采购成本 ⇒ 100 / 0.61 = 163.93
    assert without_loss == COST_FLOOR_WITHOUT_LOSS
    assert without_loss == (PURCHASE_COST / DENOMINATOR).quantize(Decimal("0.01"))
    # 有两率 ⇒ 分子乘 1.25 ⇒ 125 / 0.61 = 204.92
    assert with_loss == COST_FLOOR

    # 比值 = 分子乘数（1.25）。
    # ⚠️ 若分母也扣了这两个率，比值会是 1.25 × 0.61 / 0.36 ≈ 2.12 —— 一眼可辨。
    assert abs(with_loss / without_loss - LOSS_MULTIPLIER) < Decimal("0.001")


def test_raising_only_one_loss_rate_scales_the_floor_by_the_multiplier():
    """只动一个率 ⇒ 底线只按新的乘数变（分母依旧没动）。"""
    # 退货率 0.15 → 0.30：乘数 1.25 → 1.40 ⇒ 140 / 0.61 = 229.51
    raised = _floor(spu_return_loss_rate=Decimal("0.30"))
    assert raised == Decimal("229.51")
    assert raised == (
        PURCHASE_COST * (Decimal("1") + Decimal("0.30") + DAMAGE_RATE) / DENOMINATOR
    ).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# 3 · 两率任一为空 ⇒ 报缺且不算底线（不放宽）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        {"spu_return_loss_rate": None},
        {"spu_damage_rate": None},
        {"spu_return_loss_rate": None, "spu_damage_rate": None},
    ],
    ids=["no_return_rate", "no_damage_rate", "neither"],
)
def test_missing_spu_rates_block_the_cost_floor(missing):
    """两率任一为空 ⇒ `missing_spu_rates`，且**不算底线**。

    ⚠️ 不放宽：不能把 None 当 0 代入分子（那会算出一个偏乐观的底线）。
    """
    out = _pricing(**missing)

    assert "missing_spu_rates" in out["min_selling_price_missing_reasons"]
    assert out["min_selling_price_source"] == "discount_guard"
    # 纪律线 = 参考售价 20 × (1 − 0.10) = 18.00
    assert out["min_selling_price"] == pytest.approx(18.00, abs=0.01)
    # 有两率时才是成本线
    ok = _pricing()
    assert "missing_spu_rates" not in ok["min_selling_price_missing_reasons"]
    assert ok["min_selling_price_source"] == "cost_floor"


def test_unbound_spu_is_still_distinguished_from_missing_rates():
    """没绑 SPU ⇒ `missing_spu_binding`（不是 `missing_spu_rates`）。"""
    out = _pricing(spu_bound=False)
    assert "missing_spu_binding" in out["min_selling_price_missing_reasons"]
    assert "missing_spu_rates" not in out["min_selling_price_missing_reasons"]


# ---------------------------------------------------------------------------
# 4 · 尾程直接进分子（不再成对）
# ---------------------------------------------------------------------------


def test_delivery_cost_enters_the_numerator_directly():
    """尾程**直接进分子**：有尾程 ⇒ 底线变高。

    分子 = (100 + 10) × 1.25 = 137.50 ⇒ 137.50 / 0.61 = 225.41
    """
    without = _floor()
    with_delivery = _floor(delivery_cost=Decimal("10"))

    assert with_delivery > without
    assert with_delivery == Decimal("225.41")
    assert with_delivery == (
        (PURCHASE_COST + Decimal("10")) * LOSS_MULTIPLIER / DENOMINATOR
    ).quantize(Decimal("0.01"))


def test_retired_delivery_rate_split_is_not_reported_anymore():
    """「尾程占收入比」与「成对生效」已退役 ⇒ 不得再报那条缺料。"""
    out = _pricing(delivery_cost=Decimal("10"), free_shipping=True)

    assert (
        "missing_delivery_cost_rate_split"
        not in out["min_selling_price_missing_reasons"]
    )
    # 尾程有值且包邮 ⇒ 进分子
    assert out["delivery_cost_in_cost_floor"] is True
    assert out["cost_floor_delivery_cost"] == pytest.approx(10.0)
    # 返回值里不再有那个退役字段
    assert "cost_floor_delivery_cost_rate" not in out


def test_missing_delivery_cost_is_still_reported():
    """包邮却没配尾程 ⇒ 仍然报 `missing_delivery_cost`（尾程是必付成本）。"""
    out = _pricing(free_shipping=True)
    assert "missing_delivery_cost" in out["min_selling_price_missing_reasons"]
    assert out["delivery_cost_in_cost_floor"] is False


# ---------------------------------------------------------------------------
# 5 · 履约按件成本进分子
# ---------------------------------------------------------------------------


def test_fulfillment_costs_enter_the_numerator():
    """头程 / 仓储 / 贴单都进分子。

    分子 = (10 + 3 + 2 + 1) × 1.25 = 20.00 ⇒ 20.00 / 0.61 = 32.79
    """
    floor = _floor(
        purchase_cost=Decimal("10"),
        logistics_cost=Decimal("3"),
        storage_cost=Decimal("2"),
        label_fee=Decimal("1"),
    )
    assert floor == Decimal("32.79")
    assert floor == (
        (Decimal("10") + Decimal("3") + Decimal("2") + Decimal("1"))
        * LOSS_MULTIPLIER
        / DENOMINATOR
    ).quantize(Decimal("0.01"))


def test_fulfillment_costs_are_reported_in_the_pricing_payload():
    """履约成本要在返回值里报出来（None = 未计入，不是「这项不要钱」）。"""
    out = _pricing(
        purchase_cost=Decimal("10"),
        logistics_cost=Decimal("3"),
        storage_cost=Decimal("2"),
        label_fee=Decimal("1"),
    )
    assert out["cost_floor_logistics_cost"] == pytest.approx(3.0)
    assert out["cost_floor_storage_cost"] == pytest.approx(2.0)
    assert out["cost_floor_label_fee"] == pytest.approx(1.0)

    missing = _pricing(purchase_cost=Decimal("10"))
    assert missing["cost_floor_logistics_cost"] is None
    assert missing["cost_floor_storage_cost"] is None
    assert missing["cost_floor_label_fee"] is None


# ---------------------------------------------------------------------------
# 6 · 退役钉死：compute_cost_floor 不再接受 delivery_cost_rate
# ---------------------------------------------------------------------------


def test_compute_cost_floor_no_longer_accepts_delivery_cost_rate():
    """「尾程占收入比」入参已退役 —— 传进去必须**报错**，不能被静默忽略。

    ⚠️ 静默忽略最危险：调用方以为尾程配了 ⇒ 底线算得偏低 ⇒ 定价偏低 ⇒ 亏本。
    """
    with pytest.raises(TypeError):
        compute_cost_floor(
            purchase_cost=PURCHASE_COST,
            platform_fee_rate=PLATFORM_FEE_RATE,
            other_cost_rate=OTHER_COST_RATE,
            creator_commission_rate=CREATOR_COMMISSION_RATE,
            spu_return_loss_rate=RETURN_LOSS_RATE,
            spu_damage_rate=DAMAGE_RATE,
            target_margin_rate=TARGET_MARGIN_RATE,
            delivery_cost_rate=Decimal("0.10"),
        )


def test_compute_sku_pricing_no_longer_accepts_delivery_cost_rate():
    """SKU 定价入口同样不再接受退役入参。"""
    with pytest.raises(TypeError):
        compute_sku_pricing(
            purchase_cost=PURCHASE_COST,
            reference_selling_price=Decimal("20"),
            creator_commission_rate=None,
            platform_creator_commission_rate=CREATOR_COMMISSION_RATE,
            platform_fee_rate=PLATFORM_FEE_RATE,
            other_cost_rate=OTHER_COST_RATE,
            spu_bound=True,
            spu_return_loss_rate=RETURN_LOSS_RATE,
            spu_damage_rate=DAMAGE_RATE,
            policy=_policy(),
            deepest_policy=_policy(),
            min_selling_price_override=None,
            delivery_cost_rate=Decimal("0.10"),
        )
