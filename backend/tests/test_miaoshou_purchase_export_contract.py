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
    # page.expect_download 包裹 _click_export_button_in_dialog 是核心等待原语
    assert "async with page.expect_download(" in source
    # expect_download 的 context 内必须包含触发点击（否则 download 永不触发）
    expect_download_idx = source.index("async with page.expect_download(")
    click_export_idx = source.index("await self._click_export_button_in_dialog(page)")
    assert expect_download_idx < click_export_idx, (
        "expect_download 必须包裹 _click_export_button_in_dialog 才能捕获 download 事件"
    )


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


def test_miaoshou_purchase_export_wait_search_results_uses_existing_text():
    """_wait_search_results_ready must wait for texts that exist on current miaoshou page.

    Regression test: miaoshou removed the "采购单信息" row-group header label during a
    site refactor. The previous `_wait_search_results_ready` still waited on it and
    timed out 15s after every successful search click. Replaced with "商品信息"
    (row-group header that remains visible) and the "导入/导出" button (matches
    inventory_export._wait_search_results_ready design).
    """
    import inspect

    from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport

    source = inspect.getsource(MiaoshouPurchaseExport._wait_search_results_ready)
    # Removed text must NOT be queried (miaoshou no longer renders it).
    assert 'get_by_text("采购单信息"' not in source, (
        "miaoshou no longer renders '采购单信息' — must not be queried"
    )
    # Replacement wait targets MUST be present (verified via screenshot inspection).
    assert 'get_by_text("商品信息"' in source, (
        "'商品信息' (row-group header) must be a wait target"
    )
    assert 'name="导入/导出"' in source, (
        "'导入/导出' button must be a wait target (matches inventory design)"
    )


def test_miaoshou_purchase_export_trigger_uses_expect_download_no_nav_poll():
    """_trigger_async_export_and_download must use page.expect_download (mirrors orders/inventory).

    Regression test for production failures efd6f74e (Sep 13 23:33:34) and
    188176b7 / 9575d546 (Sep 14 01:10:44 / 01:12:15). The previous design navigated
    to /purchase/export_record and polled for "可下载"/"导出成功" text in the table,
    but miaoshou's /purchase/export_record page either redirects, hasn't loaded the
    expected text within 15s, or doesn't render the table content at all — every
    poll iteration after the first hit ``get_by_text("导出记录").first to be visible``
    15000ms timeout.

    The orders (MiaoshouOrdersExportBase.run) and inventory (MiaoshouInventoryExport.run)
    components solved the same problem by wrapping the export-button click in
    ``page.expect_download(...)``: the browser fires a download event when the file
    is ready on the server, regardless of UI state.

    This contract test enforces:
      1. _trigger_async_export_and_download uses ``page.expect_download`` (not nav+poll)
      2. Removed helpers (_navigate_to_export_record, _poll_export_record_until_ready,
         _click_download_in_export_record) are GONE
      3. expect_download wraps _click_export_button_in_dialog (download fires on click)
      4. NO _close_progress_dialog call inside expect_download context (mirror orders/inventory)
    """
    import inspect

    from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport

    source = inspect.getsource(MiaoshouPurchaseExport._trigger_async_export_and_download)
    # expect_download is the wait primitive (mirror orders/inventory).
    assert "async with page.expect_download(" in source, (
        "purchase export must use page.expect_download to wait for the file download event"
    )
    # expect_download wraps the click that triggers the backend export.
    expect_idx = source.index("async with page.expect_download(")
    click_idx = source.index("await self._click_export_button_in_dialog(page)")
    assert expect_idx < click_idx, (
        "expect_download must wrap _click_export_button_in_dialog (download fires on click)"
    )

    full_source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")
    # Removed helpers MUST NOT exist (they were the source of the bug).
    assert "async def _navigate_to_export_record(" not in full_source, (
        "_navigate_to_export_record removed — navigation to /purchase/export_record timed out"
    )
    assert "async def _poll_export_record_until_ready(" not in full_source, (
        "_poll_export_record_until_ready removed — polling /purchase/export_record timed out"
    )
    assert "async def _click_download_in_export_record(" not in full_source, (
        "_click_download_in_export_record removed — replaced by expect_download pattern"
    )
    # _close_progress_dialog must NOT exist (mirrors orders/inventory: download fires
    # independently of UI dialog state, no need to close "正在导出包裹" overlay).
    assert "async def _close_progress_dialog(" not in full_source, (
        "_close_progress_dialog removed — orders/inventory don't close progress dialog; "
        "download event is independent of UI overlay state"
    )
    # _close_progress_dialog must NOT be called inside _trigger_async_export_and_download.
    expect_block = source[source.index("async with page.expect_download("):]
    expect_end = expect_block.index("download = await dl_info.value")
    inside_expect = expect_block[:expect_end]
    assert "_close_progress_dialog" not in inside_expect, (
        "_close_progress_dialog must NOT be called inside expect_download context "
        "(mirror orders/inventory: download fires independently of UI state)"
    )
