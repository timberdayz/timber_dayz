from datetime import date

from backend.services.product_center_service import advance_inventory_age, canonical_sku_key


def test_inventory_age_resets_when_snapshot_quantity_increases():
    result = advance_inventory_age(
        snapshot_date=date(2026, 9, 15),
        current_qty=150,
        previous_qty=100,
        previous_anchor_date=date(2026, 9, 1),
    )
    assert result == {
        "age_anchor_date": date(2026, 9, 15),
        "age_days": 0,
        "reset_reason": "restocked",
    }


def test_inventory_age_carries_anchor_when_quantity_does_not_increase():
    result = advance_inventory_age(
        snapshot_date=date(2026, 9, 15),
        current_qty=80,
        previous_qty=100,
        previous_anchor_date=date(2026, 9, 1),
    )
    assert result["age_anchor_date"] == date(2026, 9, 1)
    assert result["age_days"] == 14
    assert result["reset_reason"] == "no_restock"


def test_inventory_age_does_not_age_zero_inventory():
    result = advance_inventory_age(
        snapshot_date=date(2026, 9, 15),
        current_qty=0,
        previous_qty=10,
        previous_anchor_date=date(2026, 9, 1),
    )
    assert result["age_days"] == 0
    assert result["reset_reason"] == "out_of_stock"


def test_canonical_sku_key_prefers_platform_sku_and_skips_empty_values():
    assert canonical_sku_key({"platform_sku": "  SKU-1 ", "product_sku": "SKU-2"}) == "SKU-1"
    assert canonical_sku_key({"platform_sku": "", "product_sku": None, "sku_id": "SKU-3"}) == "SKU-3"
    assert canonical_sku_key({}) is None


def test_product_center_router_exposes_spu_and_sku_resources():
    from backend.domains.business.routers.product_center import router

    paths = {route.path for route in router.routes}
    assert "/api/spus" in paths
    assert "/api/skus" in paths
    assert "/api/spus/{spu}/skus" in paths
    assert "/api/cost-assumption-profiles" in paths
    assert "/api/product-profit-estimates" in paths
    assert "/api/spu-operating" in paths
    assert router.dependencies
