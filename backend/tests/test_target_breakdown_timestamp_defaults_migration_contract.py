from pathlib import Path


def _find_target_breakdown_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*target_breakdown*timestamp*default*.py"))
    assert matches, "expected a target_breakdown timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_target_breakdown_timestamp_default_migration_exists():
    _find_target_breakdown_timestamp_default_migration()


def test_target_breakdown_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_target_breakdown_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "a_class.target_breakdown" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
    assert "WHERE created_at IS NULL" in source
    assert "WHERE updated_at IS NULL" in source
