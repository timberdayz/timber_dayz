from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _load_service_module():
    try:
        return import_module("backend.services.follow_investment_service")
    except ModuleNotFoundError as exc:
        pytest.fail(f"follow investment service module missing: {exc}")


@pytest.mark.asyncio
async def test_list_investments_filters_records_by_period_month_window():
    module = _load_service_module()
    db = SimpleNamespace(execute=AsyncMock())
    service = module.FollowInvestmentService(db)

    async def fake_execute(stmt):
        sql = str(stmt)
        assert "follow_investments" in sql
        assert "contribution_date" in sql
        assert "withdraw_date" in sql
        params = stmt.compile().params
        assert str(params["contribution_date_1"]) == "2026-04-30"
        assert str(params["withdraw_date_1"]) == "2026-04-01"
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    service._load_user_names = AsyncMock(return_value={})
    db.execute = AsyncMock(side_effect=fake_execute)

    payload = await service.list_investments(
        platform_code="shopee",
        shop_id="shop-1",
        status="active",
        period_month="2026-04",
    )

    assert payload == []
