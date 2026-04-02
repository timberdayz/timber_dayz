from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_main_shop_account_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*main*shop*account*domain*chain*.py"))
    assert matches, "expected a main/shop account domain-chain migration in migrations/versions"
    return matches[-1]


def test_main_shop_account_migration_exists():
    _find_main_shop_account_migration()


def test_main_shop_account_migration_mentions_new_tables_and_old_source_table():
    migration_path = _find_main_shop_account_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "main_accounts" in source
    assert "shop_accounts" in source
    assert "shop_account_aliases" in source
    assert "shop_account_capabilities" in source
    assert "platform_shop_discoveries" in source
    assert "platform_accounts" in source


def test_main_shop_account_migration_has_single_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
