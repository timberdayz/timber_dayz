from pathlib import Path


def _find_public_system_tables_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*public*system*timestamp*default*.py"))
    assert matches, "expected a public system tables timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_public_system_tables_timestamp_default_migration_exists():
    _find_public_system_tables_timestamp_default_migration()


def test_public_system_tables_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_public_system_tables_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "system_logs" in source
    assert "security_config" in source
    assert "smtp_config" in source
    assert "system_config" in source
    assert "created_at" in source or "updated_at" in source
    assert "SET DEFAULT now()" in source
