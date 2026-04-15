from pathlib import Path


def _find_core_runtime_tables_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*core*runtime*timestamp*default*.py"))
    assert matches, "expected a core runtime tables timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_core_runtime_tables_timestamp_default_migration_exists():
    _find_core_runtime_tables_timestamp_default_migration()


def test_core_runtime_tables_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_core_runtime_tables_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "account_aliases" in source
    assert "collection_configs" in source
    assert "collection_sync_points" in source
    assert "component_versions" in source
    assert "platform_accounts" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
