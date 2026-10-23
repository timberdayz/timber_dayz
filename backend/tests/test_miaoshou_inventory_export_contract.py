from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_export import (
    MiaoshouInventoryExport,
)
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation


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


def test_miaoshou_inventory_export_reuses_navigation_component_instead_of_opening_login():
    """导出组件必须复用导航组件走「仓库清单」，不得自己 goto 登录页。

    行为验证在 ``test_miaoshou_inventory_export_v2_flow.py``（用替身组件断言
    步骤调用序列）；此处只锁住「持有导航组件」这个结构事实。
    """
    component = MiaoshouInventoryExport(_ctx())

    assert isinstance(component.navigation_component, MiaoshouNavigation)
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"


def test_miaoshou_navigation_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx(), InventorySelectors())
    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"
