from pathlib import Path

from backend.models import database as db_module


def test_wave_one_runtime_table_family_matches_expected_runtime_schema():
    expected = {
        "catalog_files": "public",
        "collection_tasks": "core",
        "collection_task_logs": "core",
        "task_center_tasks": "public",
        "task_center_logs": "public",
        "task_center_links": "public",
    }

    for table_name, schema_name in expected.items():
        assert db_module.resolve_runtime_table_schema(table_name) == schema_name


def test_wave_one_runtime_time_columns_match_operational_freshness_columns():
    assert db_module.resolve_runtime_time_column("catalog_files") == "first_seen_at"
    assert db_module.resolve_runtime_time_column("collection_tasks") == "created_at"
    assert db_module.resolve_runtime_time_column("collection_task_logs") == "timestamp"
    assert db_module.resolve_runtime_time_column("task_center_tasks") == "created_at"
    assert db_module.resolve_runtime_time_column("task_center_logs") == "created_at"


def test_verify_restore_uses_runtime_schema_and_runtime_time_helpers_for_wave_one_tables():
    verify_restore = Path("scripts/verify_restore.py").read_text(encoding="utf-8")

    assert "qualify_runtime_table_name" in verify_restore
    assert "resolve_runtime_time_column" in verify_restore
    assert 'MAX(created_at)' not in verify_restore
