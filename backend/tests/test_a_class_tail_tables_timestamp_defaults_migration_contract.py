from pathlib import Path


def _find_a_class_tail_tables_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*a_class*tail*timestamp*default*.py"))
    assert matches, "expected an a_class tail tables timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_a_class_tail_tables_timestamp_default_migration_exists():
    _find_a_class_tail_tables_timestamp_default_migration()


def test_a_class_tail_tables_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_a_class_tail_tables_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "sales_targets_a" in source
    assert "sales_campaigns_a" in source
    assert "employee_targets" in source
    assert "attendance_records" in source
    assert "performance_config_a" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
