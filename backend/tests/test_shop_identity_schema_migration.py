from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "current_migrations" / "versions" / "20261101_shop_identity_region_and_code.py"


def test_migration_file_exists():
    assert MIGRATION.exists(), f"缺少迁移文件 {MIGRATION}"


def test_migration_adds_region_column_and_internal_code():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "shop_region" in text
    assert "internal_code" in text
    assert "NULLS NOT DISTINCT" in text, "别名唯一约束必须使用 NULLS NOT DISTINCT，否则 NULL 行互不冲突"


def test_orm_schema_has_internal_code_and_shop_region():
    text = (REPO_ROOT / "modules" / "core" / "db" / "schema_parts" / "platform.py").read_text(
        encoding="utf-8"
    )
    assert "internal_code" in text
    assert "shop_region" in text
