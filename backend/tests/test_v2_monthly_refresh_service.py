from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_v2_monthly_refresh_bootstraps_labor_before_income(monkeypatch):
    from backend.services import v2_monthly_refresh_service as module

    calls = []

    class FakeLockService:
        def __init__(self, db):
            self.db = db

        async def assert_month_mutable(self, *, year_month):
            calls.append(("lock", year_month))

    class FakePayrollService:
        def __init__(self, db):
            self.db = db

        async def generate_month(self, year_month, *, allow_pending_performance=False):
            calls.append(("payroll", year_month, allow_pending_performance))
            return {
                "employee_count": 1,
                "payroll_upserts": 1,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
            }

    class FakeLaborService:
        def __init__(self, db):
            self.db = db

        async def refresh_month(self, year_month, *, commission_by_employee_shop, commit=False):
            calls.append(("labor", year_month, commission_by_employee_shop, commit))
            return {"allocation_upserts": 2}

    class FakeBasisService:
        def __init__(self, db):
            self.db = db

        async def rebuild_month_v2(self, year_month, *, commit=False):
            calls.append(("basis", year_month, commit))
            return {"shop_count": 2}

    class FakeIncomeService:
        def __init__(self, db):
            self.db = db

        async def calculate_month(self, year_month, *, commit=False):
            calls.append(("income", year_month, commit))
            return {
                "commission_upserts": 1,
                "performance_upserts": 1,
                "commission_allocations": [
                    {
                        "employee_code": "EMP001",
                        "platform_code": "shopee",
                        "shop_id": "shop-1",
                        "commission_amount": 10,
                    }
                ],
            }

    monkeypatch.setattr(module, "PayrollPeriodLockService", FakeLockService)
    monkeypatch.setattr(module, "PayrollGenerationService", FakePayrollService)
    monkeypatch.setattr(module, "LaborCostProjectionService", FakeLaborService)
    monkeypatch.setattr(module, "ProfitBasisService", FakeBasisService)
    monkeypatch.setattr(module, "HRIncomeCalculationService", FakeIncomeService)

    db = AsyncMock()
    result = await module.V2MonthlyRefreshService(db).refresh_month("2026-08")

    assert result["calculation_passes"] == 2
    assert result["profit_basis_shop_count"] == 2
    assert calls == [
        ("lock", "2026-08"),
        ("payroll", "2026-08", True),
        ("labor", "2026-08", {}, False),
        ("basis", "2026-08", False),
        ("income", "2026-08", False),
        ("payroll", "2026-08", False),
        ("labor", "2026-08", {"EMP001": {("shopee", "shop-1"): 10.0}}, False),
        ("basis", "2026-08", False),
    ]
    db.commit.assert_awaited_once()
