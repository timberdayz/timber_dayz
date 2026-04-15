from pathlib import Path


def _find_core_dimensions_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*core*dimension*timestamp*default*.py"))
    assert matches, "expected a core dimensions timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_core_dimensions_timestamp_default_migration_exists():
    _find_core_dimensions_timestamp_default_migration()


def test_core_dimensions_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_core_dimensions_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "dim_platforms" in source
    assert "dim_products" in source
    assert "dim_product_master" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
