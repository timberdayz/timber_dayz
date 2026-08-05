from backend.domains.business.routers.expense_management import _merge_labor_cost_for_response
from unittest.mock import AsyncMock
from datetime import date as date_cls

import pytest

from backend.services.postgresql_dashboard_service import PostgresqlDashboardService


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


@pytest.mark.asyncio
async def test_business_overview_expenses_merge_manual_cost_and_system_labor_for_shop(monkeypatch):
    from backend.services import postgresql_dashboard_service as module

    class _ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class _Session:
        def __init__(self):
            self.execute = AsyncMock(side_effect=[_ScalarResult(800), _ScalarResult(350)])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    session = _Session()

    async def get_effective_month(_self):
        return "2026-08"

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        module.LaborCostPolicyService,
        "get_effective_month",
        get_effective_month,
    )

    total = await PostgresqlDashboardService()._load_operating_expenses_summary(
        date_cls(2026, 8, 1),
        platform="Shopee",
        shop_id="shop-1",
    )

    assert total == 1150.0
    manual_sql = str(session.execute.await_args_list[0].args[0])
    labor_sql = str(session.execute.await_args_list[1].args[0])
    assert '"人力费用"' in manual_sql
    assert "allocation_scope = 'shop'" in labor_sql
    assert session.execute.await_args_list[1].args[1]["platform_code"] == "shopee"
    assert session.execute.await_args_list[1].args[1]["shop_id"] == "shop-1"
