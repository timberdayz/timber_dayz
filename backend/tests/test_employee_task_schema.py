from pathlib import Path

from modules.core.db import Base


def test_employee_task_tables_are_registered():
    assert "core.employee_tasks" in Base.metadata.tables
    assert "core.employee_task_logs" in Base.metadata.tables
    assert "core.employee_task_participants" in Base.metadata.tables


def test_employee_task_table_has_core_columns():
    task_table = Base.metadata.tables["core.employee_tasks"]

    for column_name in (
        "task_id",
        "task_type",
        "task_category",
        "title",
        "status",
        "priority",
        "owner_user_id",
        "source_type",
        "source_module",
        "source_record_type",
        "source_record_id",
        "completion_schema",
        "completion_payload",
        "result_status",
        "due_at",
        "created_at",
        "updated_at",
    ):
        assert column_name in task_table.c


def test_employee_task_status_constraint_is_declared():
    task_table = Base.metadata.tables["core.employee_tasks"]

    constraints = {constraint.name for constraint in task_table.constraints}

    assert "chk_employee_tasks_status" in constraints


def test_employee_task_migration_exists():
    versions_dir = Path("migrations/versions")
    matches = list(versions_dir.glob("*employee*task*.py"))

    assert matches, "expected an employee task migration in migrations/versions"


def test_employee_task_migration_mentions_all_three_tables():
    versions_dir = Path("migrations/versions")
    migration_path = next(iter(versions_dir.glob("*employee*task*.py")))
    source = migration_path.read_text(encoding="utf-8")

    assert "employee_tasks" in source
    assert "employee_task_logs" in source
    assert "employee_task_participants" in source


def test_employee_task_migration_targets_core_schema():
    versions_dir = Path("migrations/versions")
    migration_path = next(iter(versions_dir.glob("*employee*task*.py")))
    source = migration_path.read_text(encoding="utf-8")

    assert 'CORE_SCHEMA = "core"' in source
    assert 'schema=CORE_SCHEMA' in source


def test_employee_task_tables_bind_to_core_schema():
    assert Base.metadata.tables["core.employee_tasks"].schema == "core"
    assert Base.metadata.tables["core.employee_task_logs"].schema == "core"
    assert Base.metadata.tables["core.employee_task_participants"].schema == "core"
