import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.profit_basis_service import ProfitBasisService


class _MockMappingsResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


@pytest.mark.asyncio
async def test_build_profit_basis_uses_orders_profit_minus_a_class_costs(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
        assert year_month == "2026-03"
        return {
            "shopee|shop-1": {
                "monthly_sales": 10000,
                "monthly_profit": 4000,
                "achievement_rate": 80,
            }
        }

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        if "fact_expenses_allocated_day_shop_sku" in sql:
            return _MockMappingsResult([{"a_class_cost_amount": Decimal("1500")}])
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-03",
        platform_code="Shopee",
        shop_id="shop-1",
    )

    assert basis["orders_profit_amount"] == pytest.approx(4000)
    assert basis["a_class_cost_amount"] == pytest.approx(1500)
    assert basis["b_class_cost_amount"] == pytest.approx(0)
    assert basis["profit_basis_amount"] == pytest.approx(2500)
    assert basis["basis_version"] == "A_ONLY_V1"


@pytest.mark.asyncio
async def test_build_profit_basis_clamps_negative_basis_to_zero_distributable(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
        return {
            "shopee|shop-1": {
                "monthly_sales": 8000,
                "monthly_profit": 500,
                "achievement_rate": 75,
            }
        }

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        if "fact_expenses_allocated_day_shop_sku" in sql:
            return _MockMappingsResult([{"a_class_cost_amount": Decimal("1200")}])
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-03",
        platform_code="Shopee",
        shop_id="shop-1",
    )

    assert basis["profit_basis_amount"] == pytest.approx(-700)
    assert service.calculate_distributable_amount(
        profit_basis_amount=basis["profit_basis_amount"],
        distribution_ratio=0.4,
    ) == pytest.approx(0)


@pytest.mark.asyncio
async def test_build_profit_basis_returns_zero_when_shop_metrics_missing(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
        return {}

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(return_value=_MockMappingsResult([]))

    basis = await service.build_profit_basis(
        year_month="2026-03",
        platform_code="Shopee",
        shop_id="shop-missing",
    )

    assert basis["orders_profit_amount"] == pytest.approx(0)
    assert basis["a_class_cost_amount"] == pytest.approx(0)
    assert basis["profit_basis_amount"] == pytest.approx(0)
