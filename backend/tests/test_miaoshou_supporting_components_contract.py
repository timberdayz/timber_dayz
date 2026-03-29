from pathlib import Path


def test_miaoshou_supporting_component_files_exist():
    assert Path("modules/platforms/miaoshou/components/navigation.py").exists()
    assert Path("modules/platforms/miaoshou/components/date_picker.py").exists()
    assert Path("modules/platforms/miaoshou/components/filters.py").exists()


def test_miaoshou_orders_export_reuses_supporting_components():
    source = Path("modules/platforms/miaoshou/components/orders_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "MiaoshouDatePicker" in source
    assert "MiaoshouFilters" in source
