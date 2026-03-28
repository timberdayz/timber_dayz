from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_wave1_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*schema_cleanup_wave1*.py"))
    assert matches, "expected a schema_cleanup_wave1 migration in migrations/versions"
    return matches[-1]


def test_wave1_migration_exists():
    _find_wave1_migration()


def test_wave1_migration_is_limited_to_target_breakdown_archive_rename():
    migration_path = _find_wave1_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "target_breakdown" in source
    assert "archive" in source.lower()
    assert "rename" in source.lower()
    assert "performance_config" not in source
    assert "sales_campaigns" not in source
    assert "sales_campaign_shops" not in source
    assert "drop_table" not in source.lower()


def test_alembic_has_single_head_after_wave1_migration():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert len(heads) == 1
