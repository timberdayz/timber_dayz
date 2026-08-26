from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_monthly_refresh_converges_labor_cost_before_final_income_calculation(monkeypatch):
    from backend.domains.business.routers import hr_salary

    calls = []

    class FakeIncomeService:
        def __init__(self, db):
            self.db = db

        async def calculate_month(self, year_month, *, commit=False):
            calls.append(("income", year_month, commit))
            return {
                "commission_allocations": [
                    {
                        "employee_code": "EMP001",
                        "platform_code": "shopee",
                        "shop_id": "shop-1",
                        "commission_amount": 10.0,
                    }
                ],
                "commission_upserts": len(calls),
                "performance_upserts": 1,
            }

    class FakePayrollService:
        def __init__(self, db):
            self.db = db

        async def generate_month(self, year_month):
            calls.append(("payroll", year_month))
            return {"employee_count": 1, "payroll_upserts": 1, "locked_conflicts": 0, "locked_conflict_details": []}

    class FakeLaborService:
        def __init__(self, db):
            self.db = db

        async def refresh_month(self, year_month, *, commission_by_employee_shop, commit=False):
            calls.append(("labor", year_month, commission_by_employee_shop, commit))
            return {"allocation_upserts": 1}

    class FakeProfitBasisService:
        def __init__(self, db):
            self.db = db

        async def rebuild_month_v2(self, year_month, *, commit=False):
            calls.append(("basis", year_month, commit))
            return {"year_month": year_month, "shop_count": 1}

    class FakeLockService:
        def __init__(self, db):
            self.db = db

        async def assert_month_mutable(self, *, year_month):
            calls.append(("lock", year_month))

    monkeypatch.setattr(hr_salary, "HRIncomeCalculationService", FakeIncomeService)
    monkeypatch.setattr(hr_salary, "PayrollGenerationService", FakePayrollService)
    monkeypatch.setattr(hr_salary, "LaborCostProjectionService", FakeLaborService)
    monkeypatch.setattr(hr_salary, "ProfitBasisService", FakeProfitBasisService)
    monkeypatch.setattr(hr_salary, "PayrollPeriodLockService", FakeLockService)

    db = AsyncMock()
    response = await hr_salary.refresh_payroll_records_for_month("2026-08", db=db)

    assert response["success"] is True
    assert [item[0] for item in calls] == [
        "lock",
        "income",
        "payroll",
        "labor",
        "basis",
        "income",
        "payroll",
        "labor",
    ]
    assert db.commit.await_count == 1
