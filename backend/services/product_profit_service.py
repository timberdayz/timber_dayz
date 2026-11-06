from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .product_roi_service import (
    compute_break_even_roi_lower_bound,
    compute_roi_metrics,
)


MONEY_QUANTUM = Decimal("0.01")
MEASURE_QUANTUM = Decimal("0.001")
VOLUME_QUANTUM = Decimal("0.000001")
UNIT_COST_QUANTUM = Decimal("0.000001")

TURNOVER_DAYS = {"fast": 30, "normal": 60, "slow": 90}


def reference_storage_days(turnover_class: str | None) -> int | None:
    """Return the company SKU turnover horizon in days."""
    return TURNOVER_DAYS.get(turnover_class) if turnover_class is not None else None


def build_reference_storage_cost(
    *,
    unit_volume_cbm: Decimal | int | float | None,
    unit_rate_cny_per_cbm_month: Decimal | int | float | None,
    turnover_class: str | None,
) -> Decimal | None:
    """Compute per-unit CNY storage reference; missing inputs remain missing."""
    days = reference_storage_days(turnover_class)
    if unit_volume_cbm is None or unit_rate_cny_per_cbm_month is None or days is None:
        return None
    volume = Decimal(str(unit_volume_cbm))
    rate = Decimal(str(unit_rate_cny_per_cbm_month))
    if volume < 0 or rate < 0:
        raise ValueError("storage volume and rate must be non-negative")
    return (volume * rate * Decimal(days) / Decimal("30")).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )


class BillTotalMismatchError(ValueError):
    pass


def _money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def build_logistics_sku_line(
    *,
    shipped_qty: Decimal | int | float,
    unit_weight_kg: Decimal | int | float | None,
    unit_volume_cbm: Decimal | int | float | None,
    actual_total_weight_kg: Decimal | int | float | None,
    actual_total_volume_cbm: Decimal | int | float | None,
    headhaul_cost: Decimal | int | float | None,
    handling_cost: Decimal | int | float | None,
    last_mile_cost: Decimal | int | float | None,
) -> dict[str, Decimal | None]:
    quantity = Decimal(str(shipped_qty))
    if quantity <= 0:
        raise ValueError("shipped_qty must be greater than zero")
    calculated_weight = (quantity * Decimal(str(unit_weight_kg or 0))).quantize(
        MEASURE_QUANTUM
    )
    calculated_volume = (quantity * Decimal(str(unit_volume_cbm or 0))).quantize(
        VOLUME_QUANTUM
    )
    headhaul = _money(headhaul_cost)
    handling = _money(handling_cost)
    last_mile = _money(last_mile_cost)
    total = headhaul + handling + last_mile
    return {
        "shipped_qty": quantity,
        "calculated_total_weight_kg": calculated_weight,
        "calculated_total_volume_cbm": calculated_volume,
        "actual_total_weight_kg": (
            Decimal(str(actual_total_weight_kg))
            if actual_total_weight_kg is not None
            else None
        ),
        "actual_total_volume_cbm": (
            Decimal(str(actual_total_volume_cbm))
            if actual_total_volume_cbm is not None
            else None
        ),
        "headhaul_cost": headhaul,
        "handling_cost": handling,
        "last_mile_cost": last_mile,
        "line_total_amount": total,
        "unit_headhaul_cost": (headhaul / quantity).quantize(UNIT_COST_QUANTUM),
        "unit_handling_cost": (handling / quantity).quantize(UNIT_COST_QUANTUM),
        "unit_last_mile_cost": (last_mile / quantity).quantize(UNIT_COST_QUANTUM),
    }


def validate_bill_total(
    header_total: Decimal | int | float, line_totals: Iterable[Decimal | int | float]
) -> None:
    expected = _money(header_total)
    actual = sum((_money(value) for value in line_totals), Decimal("0.00"))
    if actual != expected:
        raise BillTotalMismatchError(
            f"bill total mismatch: header={expected} lines={actual}"
        )


def build_baseline_profit(
    *,
    selling_price: Decimal | int | float,
    coupon_amount: Decimal | int | float | None,
    default_purchase_cost: Decimal | int | float | None,
    confirmed_logistics_cost: Decimal | int | float | None,
    assumption_logistics_cost: Decimal | int | float | None,
    storage_cost: Decimal | int | float | None,
    platform_fee_rate: Decimal | int | float | None,
    return_rate: Decimal | int | float | None,
    damage_rate: Decimal | int | float | None,
) -> dict[str, Decimal | str]:
    revenue = _money(_money(selling_price) - _money(coupon_amount))
    purchase_cost = _money(default_purchase_cost)
    if confirmed_logistics_cost is not None:
        logistics_cost = _money(confirmed_logistics_cost)
        logistics_cost_source = "confirmed_logistics_bill"
    else:
        logistics_cost = _money(assumption_logistics_cost)
        logistics_cost_source = "cost_assumption_profile"
    storage = _money(storage_cost)
    platform_fee = _money(revenue * Decimal(str(platform_fee_rate or 0)))
    return_loss = _money(revenue * Decimal(str(return_rate or 0)))
    damage_loss = _money(revenue * Decimal(str(damage_rate or 0)))
    profit = _money(
        revenue
        - purchase_cost
        - logistics_cost
        - storage
        - platform_fee
        - return_loss
        - damage_loss
    )
    return {
        "net_revenue": revenue,
        "purchase_cost": purchase_cost,
        "purchase_cost_source": "sku_default_purchase_cost",
        "logistics_cost": logistics_cost,
        "logistics_cost_source": logistics_cost_source,
        "storage_cost": storage,
        "storage_cost_source": "cost_assumption_profile",
        "platform_fee": platform_fee,
        "expected_return_loss": return_loss,
        "expected_damage_loss": damage_loss,
        "estimated_contribution_profit": profit,
        "estimated_margin_rate": (
            (profit / revenue).quantize(Decimal("0.00000001"))
            if revenue
            else Decimal("0")
        ),
    }


def build_platform_profit_preview(
    *,
    expected_selling_price: Decimal | int | float | None,
    competitor_price: Decimal | int | float | None,
    seller_coupon_amount: Decimal | int | float | None,
    purchase_cost: Decimal | int | float | None,
    expected_logistics_cost: Decimal | int | float | None,
    expected_storage_cost: Decimal | int | float | None,
    expected_label_fee: Decimal | int | float | None = None,
    actual_logistics_cost: Decimal | int | float | None,
    actual_storage_cost: Decimal | int | float | None,
    platform_fee_rate: Decimal | int | float | None,
    expected_ad_rate: Decimal | int | float | None,
    return_rate: Decimal | int | float | None,
    damage_rate: Decimal | int | float | None,
    creator_commission_rate: Decimal | int | float | None = None,
    roi_safety_margin: Decimal | int | float | None = None,
    target_roi_ceiling: Decimal | int | float | None = None,
) -> dict[str, dict[str, Decimal | str | list[str] | None]]:
    """Build side-by-side expected and actual-cost recost profit results.

    ``expected_ad_rate`` is interpreted as the share of pre-ad profit allocated
    to advertising (``ad_cost = pre_ad_profit × expected_ad_rate``), not as a
    fraction of revenue.

    ``creator_commission_rate`` 是达人佣金率（占收入的百分比）。
    达人佣金是**真实现金流出**，必须从利润里扣掉，否则利润会被系统性高估
    （高估幅度 = 收入 × 佣金率）。
    传 None 表示调用方没有这个口径，按 0 计（保持既有调用方的行为不变）。

    ``expected_label_fee`` 是收货仓仓储规则上的**每件贴单费**（可选成本）。
    传 None 表示该仓没配贴单费，按 0 计 —— **不得当成"缺输入"**：
    缺它会让 pre_ad_profit → None → 整条利润链算不出来（利润空白、completeness=incomplete）。
    口径与 ``creator_commission_rate`` 一致。缺失时 ``label_fee_source`` = ``assumed_zero``，
    前端据此提示"贴单费未配置"（利润是按 0 算的，不是"确实没有这项成本"）。

    ``roi_safety_margin`` / ``target_roi_ceiling`` 是**平台级 ROI 配置**
    （安全边际、平台可填上限）。传 None 表示调用方没有平台配置，用模块默认值
    （安全边际 0.20、上限 50）。
    ROI 在**这里**算而不是在路由里算：候选列表和单 SKU 试算走的是同一个函数，
    两边必须给出同一个数 —— 分头算必然漂移（设计稿 §2.5「实现时只写一处」）。
    """

    def optional_money(value: Decimal | int | float | None) -> Decimal | None:
        return _money(value) if value is not None else None

    def calculated_profit(*values: Decimal | None) -> Decimal | None:
        if any(value is None for value in values):
            return None
        revenue_value, *costs = values
        return _money(revenue_value - sum(costs, Decimal("0")))

    selling_price = optional_money(expected_selling_price)
    coupon = _money(seller_coupon_amount)
    revenue = _money(selling_price - coupon) if selling_price is not None else None
    purchase = optional_money(purchase_cost)
    expected_logistics = optional_money(expected_logistics_cost)
    expected_storage = optional_money(expected_storage_cost)
    expected_label_fee = optional_money(expected_label_fee)
    # 贴单费是**可选**的每件费用：收货仓的 active 仓储规则没配就是 0，不是"缺输入"。
    # ⚠️ 别把它当缺输入 —— 那会让 pre_ad_profit 变 None，整条利润链算不出来（利润空白）。
    label_fee_for_calc = (
        expected_label_fee if expected_label_fee is not None else Decimal("0")
    )
    label_fee_source = (
        "warehouse_rule" if expected_label_fee is not None else "assumed_zero"
    )
    platform_fee = (
        _money(revenue * Decimal(str(platform_fee_rate)))
        if revenue is not None and platform_fee_rate is not None
        else None
    )
    creator_commission = (
        _money(revenue * Decimal(str(creator_commission_rate)))
        if revenue is not None and creator_commission_rate is not None
        else Decimal("0")
    )
    return_loss = (
        _money(revenue * Decimal(str(return_rate)))
        if revenue is not None and return_rate is not None
        else None
    )
    damage_loss = (
        _money(revenue * Decimal(str(damage_rate)))
        if revenue is not None and damage_rate is not None
        else None
    )

    def _pre_ad_components(use_actual: bool) -> list[Decimal | None]:
        logistics = (
            actual_logistics_cost
            if use_actual and actual_logistics_cost is not None
            else expected_logistics
        )
        storage = (
            actual_storage_cost
            if use_actual and actual_storage_cost is not None
            else expected_storage
        )
        return [
            purchase,
            logistics,
            storage,
            label_fee_for_calc,
            platform_fee,
            creator_commission,
            return_loss,
            damage_loss,
        ]

    def _pre_ad_profit_upper_bound(use_actual: bool) -> Decimal | None:
        """广告前利润的**上界**：把未知成本一律当 0 算。

        未知成本（缺物流规则 / 缺仓储规则 / 没绑 SPU …）的真值 ≥ 0，
        所以「当 0」算出来的利润只会**大于**真值 ⇒ 它是上界。

        用途（阶段 2.2 护栏）：成本不全时 ``break_even_roi`` 算不出来，
        但仍能给出保本 ROI 的**下界**（见 ``compute_break_even_roi_lower_bound``），
        用来**证明**「运营填的目标 ROI 连最乐观的保本线都够不着 ⇒ 必亏」。

        ⚠️ 这是**证明**，不是估算：上界偏松 ⇒ 下界偏小 ⇒ 只能用来"证死"，
        不能用来"证活"。证不出来就不拦（交给 ``roi_cost_incomplete``）。
        """
        if revenue is None:
            return None
        components = _pre_ad_components(use_actual)
        return revenue - sum(
            (c if c is not None else Decimal("0")) for c in components
        )

    def _ad_cost_and_profit(
        use_actual: bool,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """返回 ``(ad_cost, profit, pre_ad_profit)``。

        ``pre_ad_profit`` 是**广告前利润**（扣完采购/物流/仓储/贴单/平台佣金/达人佣金/
        货损/退货，但**没扣广告费**）。它是 ROI 计算的分母，必须暴露出去 ——
        以前它只作为中间变量存在，算完就被丢掉，导致 ROI 只能在外层重算一遍成本
        （口径必然漂移）。
        """
        components = _pre_ad_components(use_actual)
        if revenue is None or any(c is None for c in components):
            return None, None, None
        pre_ad_profit = revenue - sum(components, Decimal("0"))
        ad = (
            _money(pre_ad_profit * Decimal(str(expected_ad_rate)))
            if expected_ad_rate is not None
            else None
        )
        profit = _money(pre_ad_profit - ad) if ad is not None else None
        return ad, profit, pre_ad_profit

    ad_cost, expected_profit, expected_pre_ad_profit = _ad_cost_and_profit(use_actual=False)
    _, actual_profit, actual_pre_ad_profit = _ad_cost_and_profit(use_actual=True)

    def _roi_payload(metrics: dict) -> dict:
        """把 ROI 计算结果铺进 preview 段。

        两个 list 键改名为 ``roi_missing_reasons`` / ``roi_anomalies``：
        它们说的是「ROI 算不出来 / 数值异常」，和「成本资料缺失」
        （``reference_cost_missing_reasons``）是两回事，不改名会被读混。
        """
        payload = {
            key: value
            for key, value in metrics.items()
            if key not in {"missing_reasons", "anomalies"}
        }
        payload["roi_missing_reasons"] = list(metrics.get("missing_reasons") or [])
        payload["roi_anomalies"] = list(metrics.get("anomalies") or [])
        return payload

    # ROI 的分母是**广告前利润**（没扣广告费），所以两段各算一次。
    # 分母算不出来（成本缺一项）时 compute_roi_metrics 一律返回 None + 缺输入原因，
    # 绝不返回乐观值。
    expected_roi = compute_roi_metrics(
        net_revenue=revenue,
        pre_ad_profit=expected_pre_ad_profit,
        safety_margin=roi_safety_margin,
        target_roi_ceiling=target_roi_ceiling,
        expected_ad_rate=expected_ad_rate,
    )
    actual_roi = compute_roi_metrics(
        net_revenue=revenue,
        pre_ad_profit=actual_pre_ad_profit,
        safety_margin=roi_safety_margin,
        target_roi_ceiling=target_roi_ceiling,
        expected_ad_rate=expected_ad_rate,
    )
    # 保本 ROI 的**下界**（阶段 2.2 护栏用）：成本不全时也算得出来，
    # 用来证明"目标 ROI 连最乐观的保本线都够不着 ⇒ 这单投了就是亏"。
    expected_roi_lower_bound = compute_break_even_roi_lower_bound(
        net_revenue=revenue,
        pre_ad_profit_upper_bound=_pre_ad_profit_upper_bound(use_actual=False),
    )
    actual_roi_lower_bound = compute_break_even_roi_lower_bound(
        net_revenue=revenue,
        pre_ad_profit_upper_bound=_pre_ad_profit_upper_bound(use_actual=True),
    )
    actual_logistics = (
        optional_money(actual_logistics_cost)
        if actual_logistics_cost is not None
        else expected_logistics
    )
    actual_storage = (
        optional_money(actual_storage_cost)
        if actual_storage_cost is not None
        else expected_storage
    )

    has_actual_logistics = actual_logistics_cost is not None
    has_actual_storage = actual_storage_cost is not None
    complete_inputs = expected_profit is not None
    completeness = (
        "incomplete"
        if not complete_inputs
        else (
            "actual"
            if has_actual_logistics and has_actual_storage
            else "mixed" if has_actual_logistics or has_actual_storage else "estimated"
        )
    )
    logistics_variance = (
        _money(actual_logistics - expected_logistics)
        if has_actual_logistics
        and actual_logistics is not None
        and expected_logistics is not None
        else None
    )
    storage_variance = (
        _money(actual_storage - expected_storage)
        if has_actual_storage
        and actual_storage is not None
        and expected_storage is not None
        else None
    )
    total_variance = None
    if logistics_variance is not None or storage_variance is not None:
        total_variance = _money((logistics_variance or 0) + (storage_variance or 0))
    return {
        "expected": {
            "net_revenue": revenue,
            "purchase_cost": purchase,
            "logistics_cost": expected_logistics,
            "storage_cost": expected_storage,
            "label_fee": expected_label_fee,
            "label_fee_source": label_fee_source,
            "platform_fee": platform_fee,
            "creator_commission": creator_commission,
            "creator_commission_rate": creator_commission_rate,
            "ad_cost": ad_cost,
            "return_loss": return_loss,
            "damage_loss": damage_loss,
            "profit": expected_profit,
            # 广告前利润（**没扣广告费**）：ROI 计算的分母，见 `product_roi_service.py`
            "pre_ad_profit": expected_pre_ad_profit,
            **_roi_payload(expected_roi),
            # 保本 ROI 的**下界**（阶段 2.2 护栏用）：成本不全时也能算出来。
            # ⚠️ 它**不是**保本线本身 —— 是保本线的下界，只可能偏松，
            #    只能用来"证死"（目标 ROI 连它都够不着 ⇒ 必亏），不能用来"证活"。
            "break_even_roi_lower_bound": expected_roi_lower_bound.get(
                "break_even_roi_lower_bound"
            ),
            "break_even_roi_lower_bound_missing_reasons": list(
                expected_roi_lower_bound.get("missing_reasons") or []
            ),
            # 预估口径的完整度：成本项齐不齐（缺任何一项 → profit 为 None → incomplete）。
            # ⚠️ 这个键以前**不存在** —— 调用方 `section.get("completeness", "complete")`
            # 在 expected 段永远取到默认值 "complete"，于是同一列在 estimated 版本写
            # "complete"、在 actual_recost 版本写 "estimated/mixed/actual"，两种语义混在一列。
            "completeness": "complete" if complete_inputs else "incomplete",
            "margin_rate": (
                (expected_profit / revenue).quantize(Decimal("0.00000001"))
                if expected_profit is not None and revenue
                else None
            ),
            "competitor_price_difference": (
                _money(selling_price - Decimal(str(competitor_price)))
                if competitor_price is not None and selling_price is not None
                else None
            ),
        },
        "actual_recost": {
            "net_revenue": revenue,
            "purchase_cost": purchase,
            "logistics_cost": actual_logistics,
            "storage_cost": actual_storage,
            "label_fee": expected_label_fee,
            "label_fee_source": label_fee_source,
            "creator_commission": creator_commission,
            "creator_commission_rate": creator_commission_rate,
            "storage_cost_source": (
                "actual_storage" if has_actual_storage else "expected_fallback"
            ),
            "profit": actual_profit,
            # 广告前利润（实际物流/仓储口径，**没扣广告费**）
            "pre_ad_profit": actual_pre_ad_profit,
            **_roi_payload(actual_roi),
            # 同上：实际成本口径的保本 ROI 下界。
            "break_even_roi_lower_bound": actual_roi_lower_bound.get(
                "break_even_roi_lower_bound"
            ),
            "break_even_roi_lower_bound_missing_reasons": list(
                actual_roi_lower_bound.get("missing_reasons") or []
            ),
            "margin_rate": (
                (actual_profit / revenue).quantize(Decimal("0.00000001"))
                if actual_profit is not None and revenue
                else None
            ),
            "completeness": completeness,
        },
        "variance": {
            "logistics": logistics_variance,
            "storage": storage_variance,
            "total": total_variance,
        },
    }
