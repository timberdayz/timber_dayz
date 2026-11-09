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

    # 第三批-B：物理列名已统一为英文（ORM 属性名与物理列名一一同名）
    assert "shop_id" in columns
    assert "platform_code" in columns
    assert "year_month" in columns
    assert "rent_amount" in columns
    assert "marketing_amount" in columns
    assert "utility_amount" in columns
    assert "ai_token_amount" in columns
    assert "labor_amount" in columns
    assert "other_amount" in columns
    assert "total_amount" in columns
    assert "remark" in columns
    assert "attachments" in columns
    assert "is_locked" in columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert "deleted_at" in columns
    assert "deleted_by" in columns

    # 中文字段名全部退场（不再有 Column("中文名", ...) 的映射层）
    for legacy_column in (
        "店铺ID",
        "年月",
        "租金",
        "营销费用",
        "水电费",
        "AI Token费用",
        "人力费用",
        "其他成本",
        "成本合计",
        "备注",
        "附件",
        "是否锁定",
        "创建时间",
        "更新时间",
        "删除时间",
        "删除人",
    ):
        assert legacy_column not in columns


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
