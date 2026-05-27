from pathlib import Path

from modules.core.db import SalaryStructure


def test_salary_structure_model_allows_multiple_versions_per_employee():
    employee_code_column = SalaryStructure.__table__.c["employee_code"]
    assert employee_code_column.unique is not True


def test_hr_migration_does_not_create_employee_code_unique_on_salary_structures():
    source = Path("migrations/versions/20260130_v4_21_0_hr_module_tables.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "employee_code VARCHAR(64) NOT NULL UNIQUE" not in source
