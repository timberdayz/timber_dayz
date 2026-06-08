import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock


class _EmployeeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


def _employee(**overrides):
    base = {
        "id": 1,
        "employee_code": "EMP260005",
        "name": "叶大望",
        "gender": None,
        "birth_date": None,
        "id_type": None,
        "id_number": None,
        "avatar_url": None,
        "phone": None,
        "email": None,
        "address": None,
        "emergency_contact": None,
        "emergency_phone": None,
        "department_id": None,
        "position_id": 10,
        "manager_id": None,
        "hire_date": None,
        "probation_end_date": None,
        "regularization_date": None,
        "leave_date": None,
        "contract_type": None,
        "contract_start_date": None,
        "contract_end_date": None,
        "bank_name": None,
        "bank_account": None,
        "status": "active",
        "employee_identity_type": "employee",
        "user_id": None,
        "created_at": "2026-04-15T00:00:00",
        "updated_at": "2026-04-15T00:00:00",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_list_employees_returns_position_code_and_name():
    from backend.domains.business.routers import hr_employee

    db = AsyncMock()
    employee = _employee()
    db.execute = AsyncMock(
        return_value=_EmployeeRowsResult([(employee, "SUPV", "主管")])
    )

    rows = asyncio.run(
        hr_employee.list_employees(
            department_id=None,
            position_id=None,
            status="active",
            keyword=None,
            page=1,
            page_size=20,
            db=db,
        )
    )

    assert len(rows) == 1
    assert rows[0].employee_code == "EMP260005"
    assert rows[0].position_code == "SUPV"
    assert rows[0].position_name == "主管"
