from modules.core.db.schema import Base


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
    assert "其他成本" in columns
    assert "成本合计" in columns
    assert "备注" in columns
    assert "附件" in columns
    assert "是否锁定" in columns
