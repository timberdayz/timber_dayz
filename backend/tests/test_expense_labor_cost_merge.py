from backend.domains.business.routers.expense_management import _merge_labor_cost_for_response
from unittest.mock import AsyncMock

import pytest


def test_system_labor_cost_replaces_legacy_labor_component_in_v2_total():
    merged = _merge_labor_cost_for_response(
        stored_labor_cost=200,
        stored_total_cost=1000,
        system_labor_cost=350,
        use_system_labor_cost=True,
    )

    assert merged == {
        "labor_cost": 350.0,
        "manual_cost_total": 800.0,
        "total_cost": 1150.0,
        "labor_cost_source": "system",
    }


def test_legacy_month_keeps_manually_entered_labor_component():
    merged = _merge_labor_cost_for_response(
        stored_labor_cost=200,
        stored_total_cost=1000,
        system_labor_cost=350,
        use_system_labor_cost=False,
    )

    assert merged == {
        "labor_cost": 200.0,
        "manual_cost_total": 800.0,
        "total_cost": 1000.0,
        "labor_cost_source": "manual_legacy",
    }


@pytest.mark.asyncio
async def test_projected_labor_cost_is_applied_only_from_effective_month(monkeypatch):
    from backend.domains.business.routers import expense_management as module

    class _Mappings:
        def all(self):
            return [
                {
                    "period_month": "2026-08",
                    "platform_code": "shopee",
                    "shop_id": "shop-1",
                    "labor_cost": 350,
                }
            ]

    class _Result:
        def mappings(self):
            return _Mappings()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result())

    async def get_effective_month(*_args, **_kwargs):
        return "2026-08"

    monkeypatch.setattr(
        "backend.services.labor_cost_policy_service.LaborCostPolicyService.get_effective_month",
        get_effective_month,
    )
    items = [
        {
            "year_month": "2026-07",
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "labor_cost": 200,
            "total_cost": 1000,
        },
        {
            "year_month": "2026-08",
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "labor_cost": 200,
            "total_cost": 1000,
        },
    ]

    await module._apply_projected_labor_costs(db, items)

    assert items[0]["labor_cost"] == 200
    assert items[0]["total_cost"] == 1000
    assert items[0]["labor_cost_source"] == "manual_legacy"
    assert items[1]["labor_cost"] == 350
    assert items[1]["total_cost"] == 1150
    assert items[1]["labor_cost_source"] == "system"
