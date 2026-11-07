from pathlib import Path


def test_operating_cost_platform_code_migration_mentions_backfill_and_constraint_updates():
    migration = Path(
        "migrations/versions/20260526_add_platform_code_to_operating_costs.py"
    )
    source = migration.read_text(encoding="utf-8")

    assert "op.add_column(" in source
    assert '"platform_code"' in source
    assert "core.shop_accounts" in source
    assert "platform_shop_id" in source
    assert "shop_account_id" in source
    assert "uq_operating_costs_a_shop_month" in source
    assert 'ON CONFLICT ("platform_code", "店铺ID", "年月")' not in source


def test_operating_cost_soft_delete_migration_exists():
    migration = Path(
        "migrations/versions/20260526_add_soft_delete_to_operating_costs.py"
    )
    source = migration.read_text(encoding="utf-8")

    assert "删除时间" in source
    assert "删除人" in source
    # 软删列名是中文; 英文 deleted_at 只允许作为**索引名**出现
    # (索引沿用英文命名, 列不能 —— 否则 ORM/迁移口径会分叉)
    assert 'sa.Column("deleted_at"' not in source
    assert '"deleted_at"' not in source
    assert "ix_operating_costs_deleted_at" in source
