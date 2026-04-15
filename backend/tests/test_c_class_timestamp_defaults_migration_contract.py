from pathlib import Path


def _find_c_class_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*c_class*timestamp*default*.py"))
    assert matches, "expected a c_class timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_c_class_timestamp_default_migration_exists():
    _find_c_class_timestamp_default_migration()


def test_c_class_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_c_class_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "shop_health_scores" in source
    assert "performance_scores" in source
    assert "clearance_rankings" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
