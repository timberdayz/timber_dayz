from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_export import MiaoshouInventoryExport
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com/login"},
        logger=None,
        config={},
    )


def test_miaoshou_inventory_config_uses_inventory_snapshot_semantics():
    selectors = InventorySelectors()

    assert selectors.checklist_path == "/warehouse/checklist"
    assert selectors.data_type_dir == "inventory"
    assert "正在导出" in selectors.progress_texts
    assert "商品信息" in selectors.group_titles
    assert "其他信息" in selectors.group_titles


def test_miaoshou_inventory_export_component_declares_inventory_domain():
    assert MiaoshouInventoryExport.platform == "miaoshou"
    assert MiaoshouInventoryExport.component_type == "export"
    assert MiaoshouInventoryExport.data_domain == "inventory"


def test_miaoshou_inventory_export_constructor_uses_inventory_selectors_by_default():
    component = MiaoshouInventoryExport(_ctx())
    assert isinstance(component.sel, InventorySelectors)


def test_miaoshou_inventory_export_constructor_accepts_custom_selectors():
    selectors = InventorySelectors()
    component = MiaoshouInventoryExport(_ctx(), selectors=selectors)
    assert component.sel is selectors


def test_miaoshou_inventory_export_source_reuses_navigation_without_opening_login():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
    assert "page.goto(login_url" not in source


def test_miaoshou_inventory_export_uses_warehouse_filters_for_scope_filter():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "MiaoshouWarehouseFilters" in source
    assert "warehouse_filters_component.run(page" in source


def test_miaoshou_inventory_export_does_not_use_keyboard_escape_for_popups():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "page.keyboard.press(\"Escape\")" not in source


def test_miaoshou_navigation_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx(), InventorySelectors())
    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"
