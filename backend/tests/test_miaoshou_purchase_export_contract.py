from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com/login"},
        logger=None,
        config={},
    )


def test_miaoshou_purchase_config_uses_purchase_goods_semantics():
    selectors = PurchaseSelectors()

    assert selectors.purchase_path == "/purchase/goods"
    assert selectors.export_record_path == "/purchase/export_record"
    assert selectors.data_type_dir == "purchase"
    assert "导出全部搜索结果" in selectors.export_menu_items
    assert "采购单信息" in selectors.export_field_groups
    assert "商品信息" in selectors.export_field_groups
    assert "关联运单信息" in selectors.export_field_groups
    assert selectors.export_record_poll_timeout_s == 300
    assert selectors.export_record_poll_interval_s == 5


def test_miaoshou_purchase_export_component_declares_purchase_domain():
    assert MiaoshouPurchaseExport.platform == "miaoshou"
    assert MiaoshouPurchaseExport.component_type == "export"
    assert MiaoshouPurchaseExport.data_domain == "purchase"


def test_miaoshou_purchase_export_constructor_uses_purchase_selectors_by_default():
    component = MiaoshouPurchaseExport(_ctx())
    assert isinstance(component.sel, PurchaseSelectors)


def test_miaoshou_purchase_export_constructor_accepts_custom_selectors():
    selectors = PurchaseSelectors()
    component = MiaoshouPurchaseExport(_ctx(), selectors=selectors)
    assert component.sel is selectors


def test_miaoshou_purchase_export_source_reuses_navigation_with_purchase_target():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.PURCHASE" in source
    assert "page.goto(login_url" not in source


def test_miaoshou_purchase_export_source_uses_async_export_subroutine():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "async def _trigger_async_export_and_download(" in source
    assert "_poll_export_record_until_ready" in source or "_poll_export_record" in source
    assert "async with page.expect_download(" in source


def test_miaoshou_purchase_export_does_not_use_keyboard_escape_for_popups():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "page.keyboard.press(\"Escape\")" not in source


def test_miaoshou_purchase_export_uses_build_standard_output_root_and_build_filename():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "build_standard_output_root(self.ctx, data_type=\"purchase\", granularity=\"manual\")" in source
    assert "build_filename(" in source


def test_miaoshou_purchase_export_reuses_miaoshou_date_picker_for_create_date():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "MiaoshouDatePicker" in source


def test_miaoshou_purchase_export_uses_role_based_trigger_for_export_dropdown():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert 'page.get_by_role("button", name="导入/导出")' in source
    assert 'page.get_by_role("menuitem", name="导出全部搜索结果")' in source
