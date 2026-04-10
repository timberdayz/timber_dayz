from pathlib import Path


def test_wave_one_schema_alignment_migration_contract_exists():
    migration_source = Path("migrations/versions/20260112_v5_0_0_schema_snapshot.py").read_text(encoding="utf-8")
    task_center_source = Path("migrations/versions/20260328_add_task_center_tables.py").read_text(encoding="utf-8")

    assert "catalog_files" in migration_source
    assert "collection_tasks" in migration_source
    assert "collection_task_logs" in migration_source
    assert "task_center_tasks" in task_center_source
    assert "task_center_logs" in task_center_source
    assert "task_center_links" in task_center_source


def test_wave_one_migration_contract_mentions_runtime_time_columns():
    migration_source = Path("migrations/versions/20260112_v5_0_0_schema_snapshot.py").read_text(encoding="utf-8")
    task_center_source = Path("migrations/versions/20260328_add_task_center_tables.py").read_text(encoding="utf-8")

    assert "first_seen_at" in migration_source
    assert "created_at" in migration_source
    assert "timestamp" in migration_source
    assert "created_at" in task_center_source


def test_wave_one_alignment_does_not_require_new_repair_migration_when_contract_is_satisfied():
    """Current wave-1 target is contract-backed by existing migrations plus runtime helpers."""
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*wave1*schema*alignment*.py"))

    assert matches == []
