"""
HR payroll route tests
"""

import asyncio
import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock


class _ResultOne:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ResultRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _load_hr_salary_module():
    return importlib.import_module("backend.routers.hr_salary")


def _json_body(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_get_salary_structure_returns_current_effective_version():
    module = _load_hr_salary_module()
    db = AsyncMock()
    current = SimpleNamespace(
        id=12,
        employee_code="EMP100",
        base_salary=1800.0,
        position_salary=200.0,
        housing_allowance=0.0,
        transport_allowance=0.0,
        meal_allowance=0.0,
        communication_allowance=0.0,
        other_allowance=0.0,
        performance_ratio=0.2,
        commission_ratio=0.05,
        social_insurance_base=1500.0,
        housing_fund_base=1500.0,
        effective_date=datetime(2025, 2, 1, tzinfo=timezone.utc).date(),
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.execute = AsyncMock(return_value=_ResultRows([current]))

    resp = asyncio.run(module.get_salary_structure("EMP100", db=db))

    assert resp.id == 12
    assert float(resp.base_salary) == 1800.0


def test_list_salary_structure_history_returns_versions_desc():
    module = _load_hr_salary_module()
    db = AsyncMock()
    rows = [
        SimpleNamespace(
            id=22,
            employee_code="EMP101",
            base_salary=2200.0,
            position_salary=300.0,
            housing_allowance=0.0,
            transport_allowance=0.0,
            meal_allowance=0.0,
            communication_allowance=0.0,
            other_allowance=0.0,
            performance_ratio=0.15,
            commission_ratio=0.03,
            social_insurance_base=1800.0,
            housing_fund_base=1800.0,
            effective_date=datetime(2025, 3, 1, tzinfo=timezone.utc).date(),
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        SimpleNamespace(
            id=21,
            employee_code="EMP101",
            base_salary=2000.0,
            position_salary=200.0,
            housing_allowance=0.0,
            transport_allowance=0.0,
            meal_allowance=0.0,
            communication_allowance=0.0,
            other_allowance=0.0,
            performance_ratio=0.1,
            commission_ratio=0.02,
            social_insurance_base=1600.0,
            housing_fund_base=1600.0,
            effective_date=datetime(2025, 1, 1, tzinfo=timezone.utc).date(),
            status="inactive",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    db.execute = AsyncMock(return_value=_ResultRows(rows))

    resp = asyncio.run(module.list_salary_structure_history("EMP101", db=db))

    assert [item.id for item in resp] == [22, 21]


def test_create_salary_structure_allows_new_version_for_same_employee():
    module = _load_hr_salary_module()
    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP102")
    structure = module.SalaryStructureCreate(
        employee_code="EMP102",
        base_salary=1200,
        position_salary=100,
        housing_allowance=0,
        transport_allowance=0,
        meal_allowance=0,
        communication_allowance=0,
        other_allowance=0,
        performance_ratio=0.1,
        commission_ratio=0.05,
        social_insurance_base=1000,
        housing_fund_base=1000,
        effective_date=datetime(2025, 4, 1, tzinfo=timezone.utc).date(),
        status="active",
    )

    db.execute = AsyncMock(side_effect=[_ResultOne(employee), _ResultOne(None)])
    def _add(obj):
        obj.id = 32
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.add = _add
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = asyncio.run(module.create_salary_structure(structure, db=db))

    assert resp.employee_code == "EMP102"
    assert float(resp.base_salary) == 1200.0


def test_update_salary_structure_updates_selected_version():
    module = _load_hr_salary_module()
    db = AsyncMock()
    record = SimpleNamespace(
        id=41,
        employee_code="EMP103",
        base_salary=1400.0,
        position_salary=100.0,
        housing_allowance=0.0,
        transport_allowance=0.0,
        meal_allowance=0.0,
        communication_allowance=0.0,
        other_allowance=0.0,
        performance_ratio=0.1,
        commission_ratio=0.05,
        social_insurance_base=1200.0,
        housing_fund_base=1200.0,
        effective_date=datetime(2025, 2, 1, tzinfo=timezone.utc).date(),
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    body = SimpleNamespace(
        model_dump=lambda exclude_unset=True: {
            "base_salary": 1550.0,
            "position_salary": 150.0,
        }
    )
    db.execute = AsyncMock(return_value=_ResultRows([record]))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    resp = asyncio.run(module.update_salary_structure("EMP103", body=body, db=db))

    assert float(resp.base_salary) == 1550.0
    assert float(resp.position_salary) == 150.0


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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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


def test_mark_payroll_record_paid_requires_confirmed_and_sets_pay_date():
    module = _load_hr_salary_module()
    db = AsyncMock()
    admin_user = SimpleNamespace(
        user_id=9001,
        is_superuser=False,
        roles=[SimpleNamespace(role_code="admin", role_name="admin")],
    )
    record = SimpleNamespace(
        id=4,
        employee_code="EMP004",
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
        status="confirmed",
        pay_date=None,
        remark=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.execute = AsyncMock(return_value=_ResultOne(record))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    audit_calls = {"count": 0, "details": None}

    async def _fake_log_action(**kwargs):
        audit_calls["count"] += 1
        audit_calls["details"] = kwargs

    module.audit_service.log_action = _fake_log_action

    resp = asyncio.run(module.mark_payroll_record_paid(4, db=db, current_user=admin_user))

    assert record.status == "paid"
    assert record.pay_date is not None
    assert db.commit.await_count == 1
    assert resp["success"] is True
    assert audit_calls["count"] == 1
    assert audit_calls["details"]["action"] == "pay"
    assert audit_calls["details"]["resource"] == "payroll_record"
    assert audit_calls["details"]["resource_id"] == "4"
    assert audit_calls["details"]["details"]["result_status"] == "paid"


def test_mark_payroll_record_paid_rejects_non_admin_user():
    module = _load_hr_salary_module()
    db = AsyncMock()
    current_user = SimpleNamespace(
        user_id=9002,
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )
    record = SimpleNamespace(id=5, status="confirmed", pay_date=None)
    db.execute = AsyncMock(return_value=_ResultOne(record))
    db.commit = AsyncMock()

    resp = asyncio.run(module.mark_payroll_record_paid(5, db=db, current_user=current_user))

    assert resp.status_code == 403
    assert _json_body(resp)["success"] is False
    assert db.commit.await_count == 0


def test_refresh_payroll_record_returns_latest_payload():
    module = _load_hr_salary_module()
    db = AsyncMock()
    record = SimpleNamespace(
        id=51,
        employee_code="EMP200",
        year_month="2025-04",
        base_salary=2000.0,
        position_salary=500.0,
        performance_salary=300.0,
        overtime_pay=50.0,
        commission=200.0,
        allowances=100.0,
        bonus=80.0,
        gross_salary=3230.0,
        social_insurance_personal=10.0,
        housing_fund_personal=10.0,
        income_tax=10.0,
        other_deductions=0.0,
        total_deductions=30.0,
        net_salary=3200.0,
        social_insurance_company=100.0,
        housing_fund_company=100.0,
        total_cost=3430.0,
        status="draft",
        pay_date=None,
        remark="ok",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class _FakeService:
        def __init__(self, db):
            self.db = db

        async def generate_employee_month(self, employee_code, year_month):
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 1,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
                "payroll_record": record,
            }

    module.PayrollGenerationService = _FakeService

    resp = asyncio.run(module.refresh_payroll_record("EMP200", "2025-04", db=db))

    assert resp["success"] is True
    assert resp["data"]["employee_code"] == "EMP200"
    assert resp["locked_conflicts"] == 0


def test_refresh_payroll_record_returns_locked_conflicts():
    module = _load_hr_salary_module()
    db = AsyncMock()

    class _FakeService:
        def __init__(self, db):
            self.db = db

        async def generate_employee_month(self, employee_code, year_month):
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 0,
                "locked_conflicts": 1,
                "locked_conflict_details": [{"employee_code": employee_code}],
                "payroll_record": None,
            }

    module.PayrollGenerationService = _FakeService

    resp = asyncio.run(module.refresh_payroll_record("EMP201", "2025-04", db=db))

    assert resp["success"] is True
    assert resp["locked_conflicts"] == 1
    assert resp["locked_conflict_details"] == [{"employee_code": "EMP201"}]
