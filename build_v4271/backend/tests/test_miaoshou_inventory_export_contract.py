from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_snapshot_export import MiaoshouInventorySnapshotExport
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={
            "label": "acc",
            "store_name": "shop",
            "login_url": "https://erp.91miaoshou.com/login",
        },
        logger=None,
        config={},
    )


def test_warehouse_config_uses_inventory_snapshot_semantics():
    selectors = WarehouseSelectors()

    assert selectors.checklist_path == "/warehouse/checklist"
    assert selectors.data_type_dir == "inventory"
    assert "正在导出" in selectors.progress_texts
    assert "商品信息" in selectors.group_titles
    assert "其他信息" in selectors.group_titles


def test_login_component_keeps_login_url_as_only_entrypoint():
    text = Path("modules/platforms/miaoshou/components/login.py").read_text(encoding="utf-8")

    assert 'get("login_url")' in text
    assert "/warehouse/checklist" not in text


def test_navigation_component_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx())

    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"


def test_inventory_snapshot_export_component_declares_inventory_domain():
    assert MiaoshouInventorySnapshotExport.platform == "miaoshou"
    assert MiaoshouInventorySnapshotExport.component_type == "export"
    assert MiaoshouInventorySnapshotExport.data_domain == "inventory"


def test_inventory_snapshot_export_source_reuses_navigation_without_opening_login():
    source = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
    assert "page.goto(login_url" not in source
