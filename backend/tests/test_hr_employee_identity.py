from pathlib import Path

from backend.schemas.hr import EmployeeResponse
from modules.core.db import Employee


def test_employee_model_exposes_identity_type():
    assert hasattr(Employee, "employee_identity_type")
    column = Employee.__table__.c["employee_identity_type"]
    assert column.nullable is False


def test_employee_response_includes_identity_type():
    payload = EmployeeResponse(
        id=1,
        employee_code="EMP260001",
        name="Alice",
        gender=None,
        birth_date=None,
        id_type=None,
        id_number=None,
        avatar_url=None,
        phone=None,
        email=None,
        address=None,
        emergency_contact=None,
        emergency_phone=None,
        department_id=None,
        position_id=None,
        manager_id=None,
        hire_date=None,
        probation_end_date=None,
        status="active",
        employee_identity_type="employee",
        created_at="2026-04-15T00:00:00",
        updated_at="2026-04-15T00:00:00",
    )
    assert payload.employee_identity_type == "employee"


def test_me_profile_auto_created_record_defaults_to_visitor():
    source = Path("backend/routers/hr_employee.py").read_text(encoding="utf-8")
    assert 'employee_identity_type="visitor"' in source
