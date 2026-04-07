from pathlib import Path


def test_alembic_env_pins_version_table_to_core_schema():
    source = Path("migrations/env.py").read_text(encoding="utf-8")

    assert 'version_table_schema="core"' in source or "version_table_schema='core'" in source
