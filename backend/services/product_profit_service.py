from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


MONEY_QUANTUM = Decimal("0.01")
MEASURE_QUANTUM = Decimal("0.001")
VOLUME_QUANTUM = Decimal("0.000001")
UNIT_COST_QUANTUM = Decimal("0.000001")


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
    actual_logistics_cost: Decimal | int | float | None,
    actual_storage_cost: Decimal | int | float | None,
    platform_fee_rate: Decimal | int | float | None,
    expected_ad_rate: Decimal | int | float | None,
    return_rate: Decimal | int | float | None,
    damage_rate: Decimal | int | float | None,
) -> dict[str, dict[str, Decimal | str | None]]:
    """Build side-by-side expected and actual-cost recost profit results."""
    selling_price = _money(expected_selling_price)
    coupon = _money(seller_coupon_amount)
    revenue = _money(selling_price - coupon)
    purchase = _money(purchase_cost)
    expected_logistics = _money(expected_logistics_cost)
    expected_storage = _money(expected_storage_cost)
    platform_fee = _money(revenue * Decimal(str(platform_fee_rate or 0)))
    ad_cost = _money(revenue * Decimal(str(expected_ad_rate or 0)))
    return_loss = _money(revenue * Decimal(str(return_rate or 0)))
    damage_loss = _money(revenue * Decimal(str(damage_rate or 0)))

    expected_profit = _money(
        revenue - purchase - expected_logistics - expected_storage - platform_fee - ad_cost - return_loss - damage_loss
    )
    actual_logistics = _money(actual_logistics_cost) if actual_logistics_cost is not None else expected_logistics
    actual_storage = _money(actual_storage_cost) if actual_storage_cost is not None else expected_storage
    actual_profit = _money(
        revenue - purchase - actual_logistics - actual_storage - platform_fee - ad_cost - return_loss - damage_loss
    )
    has_actual_logistics = actual_logistics_cost is not None
    has_actual_storage = actual_storage_cost is not None
    completeness = "actual" if has_actual_logistics and has_actual_storage else "mixed" if has_actual_logistics or has_actual_storage else "estimated"
    logistics_variance = _money(actual_logistics - expected_logistics) if has_actual_logistics else None
    storage_variance = _money(actual_storage - expected_storage) if has_actual_storage else None
    total_variance = None
    if logistics_variance is not None or storage_variance is not None:
        total_variance = _money((logistics_variance or 0) + (storage_variance or 0))
    return {
        "expected": {
            "net_revenue": revenue,
            "purchase_cost": purchase,
            "logistics_cost": expected_logistics,
            "storage_cost": expected_storage,
            "platform_fee": platform_fee,
            "ad_cost": ad_cost,
            "return_loss": return_loss,
            "damage_loss": damage_loss,
            "profit": expected_profit,
            "margin_rate": (expected_profit / revenue).quantize(Decimal("0.00000001")) if revenue else Decimal("0"),
            "competitor_price_difference": _money(selling_price - Decimal(str(competitor_price))) if competitor_price is not None else None,
        },
        "actual_recost": {
            "net_revenue": revenue,
            "purchase_cost": purchase,
            "logistics_cost": actual_logistics,
            "storage_cost": actual_storage,
            "storage_cost_source": "actual_storage" if has_actual_storage else "expected_fallback",
            "profit": actual_profit,
            "margin_rate": (actual_profit / revenue).quantize(Decimal("0.00000001")) if revenue else Decimal("0"),
            "completeness": completeness,
        },
        "variance": {
            "logistics": logistics_variance,
            "storage": storage_variance,
            "total": total_variance,
        },
    }
