from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_dim_shops_public_retirement_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*dim_shops*archive*.py"))
    assert matches, "expected a dim_shops public retirement migration in migrations/versions"
    return matches[-1]


def test_dim_shops_public_retirement_migration_exists():
    _find_dim_shops_public_retirement_migration()


def test_dim_shops_public_retirement_migration_archives_without_drop():
    migration_path = _find_dim_shops_public_retirement_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "public.dim_shops" in source
    assert "archive" in source.lower()
    assert "rename" in source.lower()
    assert "drop_table" not in source.lower()


def test_alembic_has_single_head_after_dim_shops_public_retirement_migration():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
