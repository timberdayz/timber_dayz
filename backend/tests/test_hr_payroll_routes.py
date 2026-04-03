"""
HR payroll route tests
"""

import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock


class _ResultOne:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _load_hr_salary_module():
    return importlib.import_module("backend.routers.hr_salary")


def _json_body(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_confirm_payroll_record_marks_draft_as_confirmed():
    module = _load_hr_salary_module()
    db = AsyncMock()
    record = SimpleNamespace(
        id=1,
        employee_code="EMP001",
        year_month="2025-01",
        base_salary=1000.0,
        position_salary=200.0,
        performance_salary=100.0,
        overtime_pay=0.0,
        commission=50.0,
        allowances=20.0,
        bonus=0.0,
        gross_salary=1370.0,
        social_insurance_personal=10.0,
        housing_fund_personal=10.0,
        income_tax=5.0,
        other_deductions=0.0,
        total_deductions=25.0,
        net_salary=1345.0,
        social_insurance_company=30.0,
        housing_fund_company=30.0,
        total_cost=1430.0,
        status="draft",
        pay_date=None,
        remark=None,
        created_at=None,
        updated_at=None,
    )
    db.execute = AsyncMock(return_value=_ResultOne(record))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    resp = asyncio.run(module.confirm_payroll_record(1, db=db))

    assert record.status == "confirmed"
    assert db.commit.await_count == 1
    assert resp["success"] is True


def test_update_payroll_record_rejects_confirmed_record():
    module = _load_hr_salary_module()
    db = AsyncMock()
    record = SimpleNamespace(id=2, status="confirmed")
    db.execute = AsyncMock(return_value=_ResultOne(record))
    body = SimpleNamespace(
        model_dump=lambda exclude_unset=True: {"bonus": 200.0}
    )

    resp = asyncio.run(module.update_payroll_record(2, body=body, db=db))

    assert resp.status_code == 409
    assert _json_body(resp)["success"] is False


def test_reopen_payroll_record_rejects_paid_record():
    module = _load_hr_salary_module()
    db = AsyncMock()
    record = SimpleNamespace(id=3, status="paid")
    db.execute = AsyncMock(return_value=_ResultOne(record))

    resp = asyncio.run(module.reopen_payroll_record(3, db=db))

    assert resp.status_code == 409
    assert _json_body(resp)["success"] is False
