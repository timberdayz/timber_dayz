import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.profit_basis_service import ProfitBasisService
from modules.core.db import DimFiscalCalendar


class _MockMappingsResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
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
async def test_build_profit_basis_prefers_allocated_costs_when_rows_exist(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
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
            return _MockMappingsResult([
                {
                    "allocated_row_count": 2,
                    "a_class_cost_amount": Decimal("1500"),
                }
            ])
        if "a_class.operating_costs" in sql:
            raise AssertionError("operating_costs fallback should not run when allocated rows exist")
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-04",
        platform_code="Shopee",
        shop_id="shop-1",
    )

    assert basis["a_class_cost_amount"] == pytest.approx(1500)
    assert basis["profit_basis_amount"] == pytest.approx(2500)


@pytest.mark.asyncio
async def test_build_profit_basis_falls_back_to_operating_costs_when_allocated_rows_missing(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
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
            return _MockMappingsResult([
                {
                    "allocated_row_count": 0,
                    "a_class_cost_amount": Decimal("0"),
                }
            ])
        if "a_class.operating_costs" in sql:
            assert '"成本合计"' in sql
            assert '"删除时间" IS NULL' in sql
            assert params["year_month"] == "2026-04"
            assert params["platform_code"] == "Shopee"
            assert params["shop_id"] == "shop-1"
            return _MockMappingsResult([{"a_class_cost_amount": Decimal("24023")}])
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-04",
        platform_code="Shopee",
        shop_id="shop-1",
    )

    assert basis["orders_profit_amount"] == pytest.approx(4000)
    assert basis["a_class_cost_amount"] == pytest.approx(24023)
    assert basis["profit_basis_amount"] == pytest.approx(-20023)


@pytest.mark.asyncio
async def test_build_profit_basis_operating_cost_fallback_excludes_soft_deleted_rows(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
        return {
            "tiktok|shop-2": {
                "monthly_sales": 5000,
                "monthly_profit": 3000,
                "achievement_rate": 70,
            }
        }

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        if "fact_expenses_allocated_day_shop_sku" in sql:
            return _MockMappingsResult([
                {
                    "allocated_row_count": 0,
                    "a_class_cost_amount": Decimal("0"),
                }
            ])
        if "a_class.operating_costs" in sql:
            assert '"删除时间" IS NULL' in sql
            return _MockMappingsResult([{"a_class_cost_amount": Decimal("800")}])
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-04",
        platform_code="TikTok",
        shop_id="shop-2",
    )

    assert basis["a_class_cost_amount"] == pytest.approx(800)
    assert basis["profit_basis_amount"] == pytest.approx(2200)


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


@pytest.mark.asyncio
async def test_build_profit_basis_passes_date_objects_to_a_class_cost_query(monkeypatch):
    db = AsyncMock()
    service = ProfitBasisService(db)

    async def fake_load_shop_metrics(db_arg, year_month):
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
            assert params["period_start"].isoformat() == "2026-04-01"
            assert params["next_month"].isoformat() == "2026-05-01"
            assert not isinstance(params["period_start"], str)
            assert not isinstance(params["next_month"], str)
            return _MockMappingsResult([{"a_class_cost_amount": Decimal("1500")}])
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.load_shop_monthly_metrics",
        fake_load_shop_metrics,
    )
    db.execute = AsyncMock(side_effect=fake_execute)

    basis = await service.build_profit_basis(
        year_month="2026-04",
        platform_code="Shopee",
        shop_id="shop-1",
    )

    assert basis["profit_basis_amount"] == pytest.approx(2500)


@pytest.mark.asyncio
async def test_upsert_profit_basis_snapshot_creates_new_snapshot():
    db = AsyncMock()
    added = []
    db.add = lambda row: added.append(row)
    service = ProfitBasisService(db)

    db.execute = AsyncMock(return_value=_MockMappingsResult([]))

    payload = {
        "period_month": "2026-03",
        "platform_code": "shopee",
        "shop_id": "shop-1",
        "orders_profit_amount": 4000.0,
        "a_class_cost_amount": 1500.0,
        "b_class_cost_amount": 0.0,
        "profit_basis_amount": 2500.0,
        "basis_version": "A_ONLY_V1",
    }

    result = await service.upsert_profit_basis_snapshot(payload)

    assert result == payload
    assert len(added) == 2
    assert isinstance(added[0], DimFiscalCalendar)
    assert added[0].period_code == "2026-03"
    assert getattr(added[1], "period_month") == "2026-03"
    assert getattr(added[1], "shop_id") == "shop-1"
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_upsert_profit_basis_snapshot_updates_existing_snapshot():
    db = AsyncMock()
    db.add = lambda row: None
    service = ProfitBasisService(db)

    existing = SimpleNamespace(
        period_month="2026-03",
        platform_code="shopee",
        shop_id="shop-1",
        orders_profit_amount=100.0,
        a_class_cost_amount=50.0,
        b_class_cost_amount=0.0,
        profit_basis_amount=50.0,
        basis_version="A_ONLY_V1",
    )
    db.execute = AsyncMock(return_value=_MockMappingsResult([existing]))

    payload = {
        "period_month": "2026-03",
        "platform_code": "shopee",
        "shop_id": "shop-1",
        "orders_profit_amount": 4000.0,
        "a_class_cost_amount": 1500.0,
        "b_class_cost_amount": 0.0,
        "profit_basis_amount": 2500.0,
        "basis_version": "A_ONLY_V1",
    }

    result = await service.upsert_profit_basis_snapshot(payload)

    assert result == payload
    assert existing.orders_profit_amount == pytest.approx(4000.0)
    assert existing.a_class_cost_amount == pytest.approx(1500.0)
    assert existing.profit_basis_amount == pytest.approx(2500.0)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_fiscal_period_exists_creates_missing_period():
    db = AsyncMock()
    added = []
    db.add = lambda row: added.append(row)
    service = ProfitBasisService(db)

    db.execute = AsyncMock(return_value=_MockMappingsResult([]))

    await service.ensure_fiscal_period_exists("2026-04")

    assert len(added) == 1
    assert isinstance(added[0], DimFiscalCalendar)
    assert added[0].period_code == "2026-04"
    assert added[0].period_year == 2026
    assert added[0].period_month == 4
    assert added[0].start_date.isoformat() == "2026-04-01"
    assert added[0].end_date.isoformat() == "2026-04-30"
    assert added[0].status == "open"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_profit_basis_snapshot_ensures_period_before_insert():
    db = AsyncMock()
    added = []
    db.add = lambda row: added.append(row)
    service = ProfitBasisService(db)

    def _execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        if "FROM core.dim_fiscal_calendar" in sql:
            return _MockMappingsResult([])
        if "FROM finance.shop_profit_basis" in sql:
            return _MockMappingsResult([])
        raise AssertionError(f"unexpected SQL: {sql}")

    db.execute = AsyncMock(side_effect=_execute_side_effect)

    payload = {
        "period_month": "2026-04",
        "platform_code": "shopee",
        "shop_id": "shop-1",
        "orders_profit_amount": 0.0,
        "a_class_cost_amount": 0.0,
        "b_class_cost_amount": 0.0,
        "profit_basis_amount": 0.0,
        "basis_version": "A_ONLY_V1",
    }

    await service.upsert_profit_basis_snapshot(payload)

    assert len(added) == 2
    assert isinstance(added[0], DimFiscalCalendar)
    assert added[0].period_code == "2026-04"
    assert getattr(added[1], "period_month") == "2026-04"
    assert getattr(added[1], "shop_id") == "shop-1"
    assert db.commit.await_count == 2
