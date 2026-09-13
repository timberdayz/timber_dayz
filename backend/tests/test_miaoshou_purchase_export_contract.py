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


def test_miaoshou_purchase_config_input_names_align_with_panel_textboxes():
    """Real /purchase/goods panel textboxes are labeled 开始日期/结束日期/开始时间/结束时间 — not 创建日期/创建时间.

    Regression test for commit f28e871b which set CUSTOM_DATE_INPUT_NAMES to the
    wrong labels based on the external filter label rather than the panel internals.
    """
    from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
    selectors = PurchaseSelectors()
    assert selectors.custom_date_input_names == ("开始日期", "结束日期")
    assert selectors.custom_time_input_names == ("开始时间", "结束时间")


def test_miaoshou_purchase_export_injects_purchase_selectors_into_date_picker():
    """MiaoshouPurchaseExport must inject PurchaseSelectors (not OrdersSelectors) into MiaoshouDatePicker.

    Regression test for the bug at purchase_export.py:42.
    """
    from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
    from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport

    component = MiaoshouPurchaseExport(_ctx())
    assert isinstance(component.date_picker_component.sel, PurchaseSelectors)


def test_miaoshou_purchase_config_declares_default_tab_param_all():
    """PurchaseSelectors.purchase_tab_param defaults to "all" — drives navigation URL.

    miaoshou /purchase/goods 状态 tab 通过 ?tab={value} 切换（与 orders 用
    ?platform= 表达 subtype 的哲学一致）。默认 "all" 对应"全部" tab，避免
    依赖 UI click（purchase 状态 tab 用 role="label" 渲染，Playwright
    actionability 检查会超时）。
    """
    selectors = PurchaseSelectors()
    assert selectors.purchase_tab_param == "all"


def test_miaoshou_purchase_navigation_url_includes_default_tab_param():
    """MiaoshouNavigation._purchase_goods_url must include ?tab=all by default.

    Regression test for the bug at purchase_export.py:_select_status_tab — it was
    trying to click a label-role element which timed out. Replacing it with URL
    parameter eliminates the click failure.
    """
    from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation

    nav = MiaoshouNavigation(_ctx())
    url = nav._purchase_goods_url()
    assert url == "https://erp.91miaoshou.com/purchase/goods?tab=all"
    assert "tab=all" in url


def test_miaoshou_purchase_navigation_url_respects_custom_tab_param():
    """MiaoshouNavigation._purchase_goods_url respects selectors.purchase_tab_param."""
    from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation

    selectors = PurchaseSelectors(purchase_tab_param="draft")
    nav = MiaoshouNavigation(_ctx(), selectors)
    url = nav._purchase_goods_url()
    assert url == "https://erp.91miaoshou.com/purchase/goods?tab=draft"


def test_miaoshou_purchase_export_source_does_not_call_select_status_tab():
    """MiaoshouPurchaseExport.run must NOT call _select_status_tab.

    Status tab is now controlled by navigation URL (?tab=...). Removing the
    click-based _select_status_tab eliminates the role="label" click timeout.
    """
    import inspect

    from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport

    source = inspect.getsource(MiaoshouPurchaseExport.run)
    # check for actual invocation (not just mention in comments/docstring)
    assert "self._select_status_tab(" not in source
    assert 'get_by_role("tab"' not in source
