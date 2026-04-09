from pathlib import Path

from backend.models import database as db_module


def test_runtime_table_schema_map_prefers_actual_collection_and_public_tables():
    assert db_module.resolve_runtime_table_schema("collection_tasks") == "core"
    assert db_module.resolve_runtime_table_schema("collection_task_logs") == "core"
    assert db_module.resolve_runtime_table_schema("catalog_files") == "public"
    assert db_module.resolve_runtime_table_schema("task_center_tasks") == "public"
    assert db_module.resolve_runtime_table_schema("task_center_logs") == "public"
    assert db_module.resolve_runtime_table_schema("task_center_links") == "public"


def test_qualify_runtime_table_name_returns_schema_qualified_name_for_known_tables():
    assert db_module.qualify_runtime_table_name("catalog_files") == "public.catalog_files"
    assert db_module.qualify_runtime_table_name("collection_tasks") == "core.collection_tasks"


def test_resolve_runtime_time_column_tracks_drifted_runtime_columns():
    assert db_module.resolve_runtime_time_column("collection_task_logs") == "timestamp"
    assert db_module.resolve_runtime_time_column("catalog_files") == "first_seen_at"
    assert db_module.resolve_runtime_time_column("task_center_logs") == "created_at"
    assert db_module.resolve_runtime_time_column("collection_tasks") == "created_at"


def test_collection_runtime_scripts_do_not_hardcode_core_catalog_files():
    migrate_core_tables = Path("scripts/migrate_core_tables.py").read_text(encoding="utf-8")
    test_search_path = Path("scripts/test_search_path.py").read_text(encoding="utf-8")

    assert "SELECT COUNT(*) FROM core.catalog_files" not in migrate_core_tables
    assert "SELECT COUNT(*) FROM core.catalog_files" not in test_search_path
