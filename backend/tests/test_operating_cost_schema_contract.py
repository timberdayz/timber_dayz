from importlib import import_module

from modules.core.db.schema import Base


operating_cost_migration = import_module(
    "migrations.versions.20260521_operating_costs_add_cost_total_note_lock"
)
labor_cost_migration = import_module(
    "migrations.versions.20260609_add_labor_cost_to_operating_costs"
)


def test_operating_cost_metadata_includes_platform_and_extended_columns():
    table = Base.metadata.tables["a_class.operating_costs"]
    columns = set(table.columns.keys())

    assert "店铺ID" in columns
    assert "platform_code" in columns
    assert "年月" in columns
    assert "租金" in columns
    assert "营销费用" in columns
    assert "水电费" in columns
    assert "AI Token费用" in columns
    assert "人力费用" in columns
    assert "其他成本" in columns
    assert "成本合计" in columns
    assert "备注" in columns
    assert "附件" in columns
    assert "是否锁定" in columns


def test_operating_cost_migration_normalizes_legacy_snapshot_columns():
    source = operating_cost_migration.upgrade.__code__.co_consts
    migration_text = "\n".join(str(item) for item in source)

    for old_column, new_column in [
        ("shop_id", "店铺ID"),
        ("year_month", "年月"),
        ("rent", "租金"),
        ("salary", "工资"),
        ("utilities", "水电费"),
        ("other_costs", "其他成本"),
        ("工资", "营销费用"),
    ]:
        assert old_column in migration_text
        assert new_column in migration_text


def test_operating_cost_labor_cost_migration_adds_column_and_backfills_total():
    source = labor_cost_migration.upgrade.__code__.co_consts
    migration_text = "\n".join(str(item) for item in source)

    assert "人力费用" in migration_text
    assert "成本合计" in migration_text
