from backend.routers.inventory_domain import router
from backend.services.inventory.aging_service import (
    bucket_age_days,
    compute_weighted_avg_age_days,
)


def test_weighted_avg_age_days_uses_remaining_qty_weights():
    value = compute_weighted_avg_age_days(
        rows=[
            {"remaining_qty": 10, "age_days": 30},
            {"remaining_qty": 20, "age_days": 60},
        ]
    )
    assert round(value, 2) == 50.0


def test_bucket_age_days_maps_91_to_180_plus_correctly():
    assert bucket_age_days(95) == "91-180"


def test_inventory_domain_router_exposes_aging_routes():
    paths = {route.path for route in router.routes}
    assert "/api/inventory/aging" in paths
    assert "/api/inventory/aging/buckets" in paths
