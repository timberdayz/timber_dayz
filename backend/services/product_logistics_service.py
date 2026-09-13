from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping


def match_logistics_rule(
    rules: Iterable[Mapping],
    *,
    provider: str | None,
    warehouse_code: str | None,
    transport_type: str | None,
    cargo_class: str | None = None,
    is_sensitive: bool | None = None,
    as_of: date | None = None,
) -> Mapping | None:
    """Select the most specific active rule for a shipment context."""
    as_of = as_of or date.today()
    candidates = []
    for rule in rules:
        if rule.get("status", "active") not in ("active", True) or rule.get("active", True) is False:
            continue
        if rule.get("effective_from") and rule["effective_from"] > as_of:
            continue
        if rule.get("effective_to") and rule["effective_to"] < as_of:
            continue
        if rule.get("provider") not in (None, provider) and rule.get("logistics_provider") not in (None, provider):
            continue
        if rule.get("warehouse_code") not in (None, warehouse_code):
            continue
        if rule.get("transport_type") not in (None, transport_type):
            continue
        if rule.get("cargo_class") not in (None, cargo_class):
            continue
        if is_sensitive is not None and rule.get("is_sensitive") not in (None, is_sensitive):
            continue
        specificity = sum(
            value not in (None, "")
            for value in (
                rule.get("provider", rule.get("logistics_provider")),
                rule.get("warehouse_code"),
                rule.get("transport_type"),
                rule.get("cargo_class"),
                rule.get("is_sensitive") if is_sensitive is not None else None,
            )
        )
        effective_from = rule.get("effective_from") or date.min
        candidates.append((specificity, effective_from, rule))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def allocate_bill_line(*, line_amount: Decimal | float | int, basis: str, items: list[Mapping]) -> list[dict]:
    """Allocate a provider line to one or more SKU rows with cent reconciliation."""
    if basis not in {"volume", "weight", "quantity"}:
        raise ValueError("allocation basis must be volume, weight, or quantity")
    amount = Decimal(str(line_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    key = {"volume": "volume_cbm", "weight": "weight_kg", "quantity": "quantity"}[basis]
    weights = [Decimal(str(item.get(key) or 0)) for item in items]
    total = sum(weights, Decimal("0"))
    if not items or total <= 0:
        raise ValueError("allocation basis has no positive quantity")
    result = []
    allocated = Decimal("0")
    for index, (item, weight) in enumerate(zip(items, weights)):
        if index == len(items) - 1:
            share = amount - allocated
        else:
            share = (amount * weight / total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            allocated += share
        result.append({"sku_id": item["sku_id"], "allocation_basis": basis, "allocation_ratio": weight / total, "allocated_amount": share})
    return result
