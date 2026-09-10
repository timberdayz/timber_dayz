"""Payroll manual input contract and route tests."""

import asyncio
import importlib
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _ResultOne:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _load_module():
    return importlib.import_module("backend.domains.business.routers.hr_salary")


def _admin_user():
    return SimpleNamespace(is_superuser=True, roles=[])


def test_manual_input_contract_has_natural_key_and_all_manual_fields():
    from backend.schemas.hr import PayrollManualInputResponse, PayrollManualInputUpdate
    from modules.core.db import PayrollManualInput

    expected = {
        "employee_code",
        "year_month",
        "overtime_pay",
        "bonus",
        "social_insurance_personal",
        "housing_fund_personal",
        "income_tax",
        "other_deductions",
        "social_insurance_company",
        "housing_fund_company",
        "pay_date",
        "remark",
        "backfill_source_month",
        "backfill_note",
    }
    assert expected <= set(PayrollManualInput.__table__.c.keys())
    assert expected - {"employee_code", "year_month"} <= set(
        PayrollManualInputUpdate.model_fields
    )
    assert expected <= set(PayrollManualInputResponse.model_fields)


@pytest.mark.asyncio
async def test_manual_input_requires_admin_permission():
    module = _load_module()
    db = AsyncMock()
    response = await module.upsert_payroll_manual_input(
        "EMP001",
        "2026-08",
        body=__import__("backend.schemas.hr", fromlist=["PayrollManualInputUpdate"]).PayrollManualInputUpdate(bonus=100),
        db=db,
        current_user=SimpleNamespace(is_superuser=False, roles=[]),
    )
    assert response.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_input_saves_without_payroll_or_performance_calculation(monkeypatch):
    module = _load_module()
    from modules.core.db import Employee, PayrollRecord, PayrollManualInput
    from backend.schemas.hr import PayrollManualInputUpdate

    employee = SimpleNamespace(
        employee_code="EMP001",
        status="active",
        employee_identity_type="employee",
    )
    db = AsyncMock()
    added = []

    async def execute(stmt, *_args, **_kwargs):
        entity = None
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
        if entity is Employee:
            return _ResultOne(employee)
        if entity is PayrollRecord:
            return _ResultOne(None)
        if entity is PayrollManualInput:
            return _ResultOne(None)
        return _ResultOne(None)

    db.execute = AsyncMock(side_effect=execute)
    db.add = added.append
    db.commit = AsyncMock()
    async def refresh(record):
        record.id = 1
        record.created_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=refresh)

    class _MutableLock:
        def __init__(self, _db):
            pass

        async def assert_employee_month_mutable(self, **_kwargs):
            return None

    class _MustNotCalculate:
        def __init__(self, _db):
            raise AssertionError("manual input save must not calculate payroll")

    monkeypatch.setattr(module, "PayrollPeriodLockService", _MutableLock)
    monkeypatch.setattr(module, "HRIncomeCalculationService", _MustNotCalculate)
    monkeypatch.setattr(module, "PayrollGenerationService", _MustNotCalculate)

    response = await module.upsert_payroll_manual_input(
        "EMP001",
        "2026-08",
        body=PayrollManualInputUpdate(
            bonus=500,
            overtime_pay=120,
            pay_date=date(2026, 8, 31),
            remark="manual input",
        ),
        db=db,
        current_user=_admin_user(),
    )

    assert response["success"] is True
    record = next(item for item in added if isinstance(item, PayrollManualInput))
    assert record.employee_code == "EMP001"
    assert record.year_month == "2026-08"
    assert record.bonus == 500
    assert record.overtime_pay == 120
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_input_updates_existing_draft_snapshot_and_totals(monkeypatch):
    module = _load_module()
    from modules.core.db import Employee, PayrollRecord, PayrollManualInput
    from backend.services.payroll_generation_service import PayrollGenerationService
    from backend.schemas.hr import PayrollManualInputUpdate

    employee = SimpleNamespace(
        employee_code="EMP002",
        status="active",
        employee_identity_type="employee",
    )
    payroll = SimpleNamespace(
        employee_code="EMP002",
        year_month="2026-08",
        status="draft",
        base_salary=1000,
        position_salary=100,
        performance_salary=200,
        commission=50,
        allowances=100,
        overtime_pay=0,
        bonus=0,
        social_insurance_personal=0,
        housing_fund_personal=0,
        income_tax=0,
        other_deductions=0,
        social_insurance_company=0,
        housing_fund_company=0,
    )
    manual = SimpleNamespace(
        id=1,
        employee_code="EMP002",
        year_month="2026-08",
        bonus=0,
        overtime_pay=0,
        social_insurance_personal=0,
        housing_fund_personal=0,
        income_tax=0,
        other_deductions=0,
        social_insurance_company=0,
        housing_fund_company=0,
        pay_date=None,
        remark=None,
        backfill_source_month=None,
        backfill_note=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_ResultOne(employee), _ResultOne(payroll), _ResultOne(manual)]
    )
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    class _MutableLock:
        def __init__(self, _db):
            pass

        async def assert_employee_month_mutable(self, **_kwargs):
            return None

    monkeypatch.setattr(module, "PayrollPeriodLockService", _MutableLock)
    monkeypatch.setattr(module, "PayrollGenerationService", PayrollGenerationService)

    response = await module.upsert_payroll_manual_input(
        "EMP002",
        "2026-08",
        body=PayrollManualInputUpdate(bonus=80, overtime_pay=20),
        db=db,
        current_user=_admin_user(),
    )

    assert response["success"] is True
    assert payroll.bonus == 80
    assert payroll.overtime_pay == 20
    assert payroll.gross_salary == 1550
    assert payroll.net_salary == 1550
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_manual_input_rejects_locked_payroll(monkeypatch):
    module = _load_module()
    from modules.core.db import Employee, PayrollRecord
    from backend.schemas.hr import PayrollManualInputUpdate

    employee = SimpleNamespace(
        employee_code="EMP003",
        status="active",
        employee_identity_type="employee",
    )
    payroll = SimpleNamespace(employee_code="EMP003", year_month="2026-08", status="confirmed")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ResultOne(employee), _ResultOne(payroll)])
    db.commit = AsyncMock()

    class _MutableLock:
        def __init__(self, _db):
            pass

        async def assert_employee_month_mutable(self, **_kwargs):
            return None

    monkeypatch.setattr(module, "PayrollPeriodLockService", _MutableLock)

    response = await module.upsert_payroll_manual_input(
        "EMP003",
        "2026-08",
        body=PayrollManualInputUpdate(bonus=100),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    assert "不可修改" in response.body.decode("utf-8")
    db.commit.assert_not_awaited()
