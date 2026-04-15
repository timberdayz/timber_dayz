from pathlib import Path


def _find_core_metadata_tables_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*core*metadata*timestamp*default*.py"))
    assert matches, "expected a core metadata tables timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_core_metadata_tables_timestamp_default_migration_exists():
    _find_core_metadata_tables_timestamp_default_migration()


def test_core_metadata_tables_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_core_metadata_tables_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "field_mappings" in source
    assert "field_mapping_template_items" in source
    assert "dim_currencies" in source
    assert "dim_fiscal_calendar" in source
    assert "dim_vendors" in source
    assert "created_at" in source
    assert "SET DEFAULT now()" in source
