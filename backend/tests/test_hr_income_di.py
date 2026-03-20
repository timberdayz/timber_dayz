from __future__ import annotations

from typing import Any, Dict

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.routers import hr_employee


class FakeHRIncomeService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    async def calculate_month(self, year_month: str) -> Dict[str, Any]:
        return {
            "year_month": year_month,
            "employee_count": 0,
            "commission_upserts": 0,
            "performance_upserts": 0,
            "source": "test-double",
        }


@pytest.mark.asyncio
async def test_calculate_income_uses_overridden_service(auth_headers: dict[str, str]) -> None:
    async def _dep_override() -> FakeHRIncomeService:
        return FakeHRIncomeService()

    app.dependency_overrides[hr_employee.hr_income_service_dep] = _dep_override

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
        ) as client:
            resp = await client.post(
                "/api/hr/income/calculate",
                params={"year_month": "2025-01"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["year_month"] == "2025-01"
        assert data["employee_count"] == 0
    finally:
        app.dependency_overrides.pop(hr_employee.hr_income_service_dep, None)
