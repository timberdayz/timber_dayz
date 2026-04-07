from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_public_alembic_version_archive_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*public*alembic*archive*.py"))
    assert matches, "expected a public alembic_version archive migration in migrations/versions"
    return matches[-1]


def test_public_alembic_version_archive_migration_exists():
    _find_public_alembic_version_archive_migration()


def test_public_alembic_version_archive_migration_archives_without_drop():
    migration_path = _find_public_alembic_version_archive_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "public" in source.lower()
    assert "alembic_version" in source
    assert "archive" in source.lower()
    assert "rename" in source.lower()
    assert "drop_table" not in source.lower()


def test_alembic_has_single_head_after_public_alembic_version_archive_migration():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
