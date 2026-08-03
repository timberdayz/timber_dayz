from pathlib import Path

from modules.core.db import ShopAccount


def test_shop_account_business_role_is_a_non_nullable_enum_with_operating_store_default():
    column = ShopAccount.__table__.c.business_role

    assert column.nullable is False
    assert set(column.type.enums) == {"operating_store", "collection_source"}
    assert column.default.arg == "operating_store"
    assert column.server_default.arg.text == "'operating_store'"


def test_business_role_migration_adds_core_shop_account_column_without_data_rewrite():
    migration_paths = list(Path("migrations/versions").glob("*_shop_account_business_role.py"))

    assert len(migration_paths) == 1
    source = migration_paths[0].read_text(encoding="utf-8")

    assert 'revision = "20260803_shop_account_business_role"' in source
    assert 'down_revision = "20260629_cloud_sync_receive_log"' in source
    assert '"operating_store"' in source
    assert '"collection_source"' in source
    assert '"business_role"' in source
    assert "UPDATE core.shop_accounts" not in source


def test_boundary_cleanup_migration_marks_known_collection_source_and_repairs_active_allocations():
    migration_paths = list(Path("migrations/versions").glob("*_boundary_data_cleanup.py"))

    assert len(migration_paths) == 1
    source = migration_paths[0].read_text(encoding="utf-8")

    assert "miaoshou_real_001" in source
    assert "collection_source" in source
    assert "enabled = true" in source
    assert "status = 'active'" in source
    assert "status = 'active'" in source
