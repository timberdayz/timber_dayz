from backend.tests.test_add_performance_income_acceptance import (
    test_my_income_linked_uses_payroll_net_salary_only_and_skips_fallback,
    test_my_income_linked_without_payroll_returns_empty_income_state,
    test_my_income_prefers_payroll_snapshot_for_approved_month,
)

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from backend.domains.business.routers.hr_employee import get_my_income

__all__ = [
    "test_my_income_linked_uses_payroll_net_salary_only_and_skips_fallback",
    "test_my_income_linked_without_payroll_returns_empty_income_state",
    "test_my_income_prefers_payroll_snapshot_for_approved_month",
    "test_my_income_marks_locked_payroll_as_stale_when_latest_calc_is_newer",
]


def test_my_income_marks_locked_payroll_as_stale_when_latest_calc_is_newer(monkeypatch):
    class _ResultOne:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _RowsResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP099", employee_identity_type="employee")
    payroll = SimpleNamespace(
        employee_code="EMP099",
        year_month="2025-01",
        base_salary=1000.0,
        position_salary=200.0,
        commission=300.0,
        net_salary=1888.0,
        performance_salary=200.0,
        allowances=100.0,
        total_deductions=12.0,
        gross_salary=1900.0,
        overtime_pay=50.0,
        bonus=50.0,
        social_insurance_personal=5.0,
        housing_fund_personal=4.0,
        income_tax=2.0,
        other_deductions=1.0,
        social_insurance_company=120.0,
        housing_fund_company=80.0,
        total_cost=2100.0,
        status="confirmed",
        updated_at="2025-01-31T08:00:00+00:00",
        created_at="2025-01-31T08:00:00+00:00",
    )
    execute_calls = {"n": 0}

    async def _execute(_stmt, _params=None):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ResultOne(employee)
        if n == 2:
            return _ResultOne(None)
        if n == 3:
            return _ResultOne(payroll)
        if n == 4:
            return _RowsResult([("2025-02-01T10:00:00+00:00",)])
        if n == 5:
            return _RowsResult([])
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    async def _fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.domains.business.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1099)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.breakdown.payroll.is_locked is True
    assert resp.breakdown.payroll.is_stale_against_latest_calc is True
    assert resp.breakdown.payroll.data_source == "payroll_record"
