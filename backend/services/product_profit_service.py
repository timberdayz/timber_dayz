from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


MONEY_QUANTUM = Decimal("0.01")
MEASURE_QUANTUM = Decimal("0.001")
VOLUME_QUANTUM = Decimal("0.000001")
UNIT_COST_QUANTUM = Decimal("0.000001")

TURNOVER_DAYS = {"fast": 30, "normal": 60, "slow": 90}


def reference_storage_days(turnover_class: str | None) -> int | None:
    """Return the company SKU turnover horizon in days."""
    return TURNOVER_DAYS.get(turnover_class) if turnover_class is not None else None


def build_reference_storage_cost(*, unit_volume_cbm: Decimal | int | float | None,
                                 unit_rate_cny_per_cbm_month: Decimal | int | float | None,
                                 turnover_class: str | None) -> Decimal | None:
    """Compute per-unit CNY storage reference; missing inputs remain missing."""
    days = reference_storage_days(turnover_class)
    if unit_volume_cbm is None or unit_rate_cny_per_cbm_month is None or days is None:
        return None
    volume = Decimal(str(unit_volume_cbm))
    rate = Decimal(str(unit_rate_cny_per_cbm_month))
    if volume < 0 or rate < 0:
        raise ValueError("storage volume and rate must be non-negative")
    return (volume * rate * Decimal(days) / Decimal("30")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


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
    calculated_weight = (quantity * Decimal(str(unit_weight_kg or 0))).quantize(MEASURE_QUANTUM)
    calculated_volume = (quantity * Decimal(str(unit_volume_cbm or 0))).quantize(VOLUME_QUANTUM)
    headhaul = _money(headhaul_cost)
    handling = _money(handling_cost)
    last_mile = _money(last_mile_cost)
    total = headhaul + handling + last_mile
    return {
        "shipped_qty": quantity,
        "calculated_total_weight_kg": calculated_weight,
        "calculated_total_volume_cbm": calculated_volume,
        "actual_total_weight_kg": Decimal(str(actual_total_weight_kg)) if actual_total_weight_kg is not None else None,
        "actual_total_volume_cbm": Decimal(str(actual_total_volume_cbm)) if actual_total_volume_cbm is not None else None,
        "headhaul_cost": headhaul,
        "handling_cost": handling,
        "last_mile_cost": last_mile,
        "line_total_amount": total,
        "unit_headhaul_cost": (headhaul / quantity).quantize(UNIT_COST_QUANTUM),
        "unit_handling_cost": (handling / quantity).quantize(UNIT_COST_QUANTUM),
        "unit_last_mile_cost": (last_mile / quantity).quantize(UNIT_COST_QUANTUM),
    }


def validate_bill_total(header_total: Decimal | int | float, line_totals: Iterable[Decimal | int | float]) -> None:
    expected = _money(header_total)
    actual = sum((_money(value) for value in line_totals), Decimal("0.00"))
    if actual != expected:
        raise BillTotalMismatchError(f"bill total mismatch: header={expected} lines={actual}")


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
    profit = _money(revenue - purchase_cost - logistics_cost - storage - platform_fee - return_loss - damage_loss)
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
        "estimated_margin_rate": (profit / revenue).quantize(Decimal("0.00000001")) if revenue else Decimal("0"),
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
) -> dict[str, dict[str, Decimal | str | None]]:
    """Build side-by-side expected and actual-cost recost profit results.

    ``expected_ad_rate`` is interpreted as the share of pre-ad profit allocated
    to advertising (``ad_cost = pre_ad_profit × expected_ad_rate``), not as a
    fraction of revenue.
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
    platform_fee = _money(revenue * Decimal(str(platform_fee_rate))) if revenue is not None and platform_fee_rate is not None else None
    return_loss = _money(revenue * Decimal(str(return_rate))) if revenue is not None and return_rate is not None else None
    damage_loss = _money(revenue * Decimal(str(damage_rate))) if revenue is not None and damage_rate is not None else None

    def _pre_ad_components(use_actual: bool) -> list[Decimal | None]:
        logistics = actual_logistics_cost if use_actual and actual_logistics_cost is not None else expected_logistics
        storage = actual_storage_cost if use_actual and actual_storage_cost is not None else expected_storage
        return [purchase, logistics, storage, expected_label_fee, platform_fee, return_loss, damage_loss]

    def _ad_cost_and_profit(use_actual: bool) -> tuple[Decimal | None, Decimal | None]:
        components = _pre_ad_components(use_actual)
        if revenue is None or any(c is None for c in components):
            return None, None
        pre_ad_profit = revenue - sum(components, Decimal("0"))
        ad = _money(pre_ad_profit * Decimal(str(expected_ad_rate))) if expected_ad_rate is not None else None
        profit = _money(pre_ad_profit - ad) if ad is not None else None
        return ad, profit

    ad_cost, expected_profit = _ad_cost_and_profit(use_actual=False)
    _, actual_profit = _ad_cost_and_profit(use_actual=True)
    actual_logistics = optional_money(actual_logistics_cost) if actual_logistics_cost is not None else expected_logistics
    actual_storage = optional_money(actual_storage_cost) if actual_storage_cost is not None else expected_storage

    has_actual_logistics = actual_logistics_cost is not None
    has_actual_storage = actual_storage_cost is not None
    complete_inputs = expected_profit is not None
    completeness = (
        "incomplete" if not complete_inputs
        else "actual" if has_actual_logistics and has_actual_storage
        else "mixed" if has_actual_logistics or has_actual_storage
        else "estimated"
    )
    logistics_variance = _money(actual_logistics - expected_logistics) if has_actual_logistics and actual_logistics is not None and expected_logistics is not None else None
    storage_variance = _money(actual_storage - expected_storage) if has_actual_storage and actual_storage is not None and expected_storage is not None else None
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
            "platform_fee": platform_fee,
            "ad_cost": ad_cost,
            "return_loss": return_loss,
            "damage_loss": damage_loss,
            "profit": expected_profit,
            "margin_rate": (expected_profit / revenue).quantize(Decimal("0.00000001")) if expected_profit is not None and revenue else None,
            "competitor_price_difference": _money(selling_price - Decimal(str(competitor_price))) if competitor_price is not None and selling_price is not None else None,
        },
        "actual_recost": {
            "net_revenue": revenue,
            "purchase_cost": purchase,
            "logistics_cost": actual_logistics,
            "storage_cost": actual_storage,
            "label_fee": expected_label_fee,
            "storage_cost_source": "actual_storage" if has_actual_storage else "expected_fallback",
            "profit": actual_profit,
            "margin_rate": (actual_profit / revenue).quantize(Decimal("0.00000001")) if actual_profit is not None and revenue else None,
            "completeness": completeness,
        },
        "variance": {
            "logistics": logistics_variance,
            "storage": storage_variance,
            "total": total_variance,
        },
    }
