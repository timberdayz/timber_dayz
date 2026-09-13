from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.warehouse_filters import MiaoshouWarehouseFilters


def test_miaoshou_warehouse_filters_component_declares_miaoshou_platform():
    assert MiaoshouWarehouseFilters.platform == "miaoshou"
    assert MiaoshouWarehouseFilters.component_type == "filters"
    assert MiaoshouWarehouseFilters.data_domain is None


def test_miaoshou_warehouse_filters_constructor_accepts_inventory_selectors():
    ctx = ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )
    selectors = InventorySelectors()
    component = MiaoshouWarehouseFilters(ctx, selectors)

    assert component.sel is selectors
