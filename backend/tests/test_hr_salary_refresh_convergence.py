from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_monthly_refresh_route_delegates_to_the_single_v2_service(monkeypatch):
    from backend.domains.business.routers import hr_salary

    calls = []

    class FakeV2MonthlyRefreshService:
        def __init__(self, db):
            self.db = db

        async def refresh_month(self, year_month):
            calls.append((self.db, year_month))
            return {
                "success": True,
                "year_month": year_month,
                "calculation_passes": 2,
            }

    monkeypatch.setattr(
        hr_salary,
        "V2MonthlyRefreshService",
        FakeV2MonthlyRefreshService,
    )
    db = AsyncMock()

    response = await hr_salary.refresh_payroll_records_for_month("2026-08", db=db)

    assert response == {
        "success": True,
        "year_month": "2026-08",
        "calculation_passes": 2,
    }
    assert calls == [(db, "2026-08")]
