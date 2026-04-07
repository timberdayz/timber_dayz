from pathlib import Path


def test_miaoshou_supporting_component_files_exist():
    assert Path("modules/platforms/miaoshou/components/navigation.py").exists()
    assert Path("modules/platforms/miaoshou/components/date_picker.py").exists()
    assert Path("modules/platforms/miaoshou/components/filters.py").exists()
    assert Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").exists()
    assert Path("modules/platforms/miaoshou/components/orders_export_base.py").exists()
    assert Path("modules/platforms/miaoshou/components/orders_shopee_export.py").exists()
    assert Path("modules/platforms/miaoshou/components/orders_tiktok_export.py").exists()


def test_miaoshou_orders_export_reuses_supporting_components():
    source = Path("modules/platforms/miaoshou/components/orders_export_base.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "MiaoshouDatePicker" in source
    assert "MiaoshouFilters" in source


def test_miaoshou_inventory_export_reuses_navigation_for_warehouse_target():
    source = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
