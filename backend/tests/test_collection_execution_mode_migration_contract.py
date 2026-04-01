from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_execution_mode_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*collection*execution_mode*.py"))
    assert matches, "expected a collection execution_mode migration in migrations/versions"
    return matches[-1]


def test_collection_execution_mode_migration_exists():
    _find_execution_mode_migration()


def test_collection_execution_mode_migration_targets_collection_configs_only():
    migration_path = _find_execution_mode_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "collection_configs" in source
    assert "execution_mode" in source
    assert "headless" in source
    assert "collection_tasks" not in source


def test_alembic_has_single_head_after_execution_mode_migration():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert len(heads) == 1
