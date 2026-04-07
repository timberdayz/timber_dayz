from pathlib import Path


def test_alembic_env_uses_64_char_version_table_column():
    source = Path("migrations/env.py").read_text(encoding="utf-8")

    assert "DefaultImpl.version_table_impl" in source
    assert 'Column("version_num", String(64), nullable=False)' in source
