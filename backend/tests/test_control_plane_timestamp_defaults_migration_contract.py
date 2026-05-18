from pathlib import Path


def _find_control_plane_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*control*plane*timestamp*default*.py"))
    assert matches, "expected a control-plane timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_control_plane_timestamp_default_migration_exists():
    _find_control_plane_timestamp_default_migration()


def test_control_plane_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_control_plane_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "employee_tasks" in source
    assert "employee_task_logs" in source
    assert "employee_task_participants" in source
    assert "sync_progress_tasks" in source
    assert "dim_rate_limit_config" in source
    assert "notification_templates" in source
    assert "alert_rules" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source


def test_control_plane_timestamp_default_migration_targets_core_employee_task_tables():
    migration_path = _find_control_plane_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert '("core", "employee_tasks")' in source
    assert '("core", "employee_task_logs")' in source
    assert '("core", "employee_task_participants")' in source
