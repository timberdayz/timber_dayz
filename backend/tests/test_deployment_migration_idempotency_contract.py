from pathlib import Path


def _read_migration(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_employee_user_id_migration_is_guarded_for_repeated_deploys():
    source = _read_migration("migrations/versions/20260130_add_user_id_to_employees.py")

    assert "_column_exists" in source
    assert "_index_exists" in source
    assert 'if not _column_exists(connection, "a_class", "employees", "user_id")' in source
    assert 'if not _index_exists(connection, "a_class", "ix_employees_user_id")' in source


def test_public_to_a_class_migration_guards_sales_targets_constraints():
    source = _read_migration("migrations/versions/20260131_migrate_public_tables_to_a_c_class.py")

    assert "constraint_exists" in source
    assert "sales_targets_pkey" in source
    assert "fk_target_breakdown_sales_targets" in source
    assert "not constraint_exists(conn, 'a_class', 'sales_targets', 'sales_targets_pkey')" in source
    assert "not constraint_exists(conn, 'a_class', 'target_breakdown', 'fk_target_breakdown_sales_targets')" in source
