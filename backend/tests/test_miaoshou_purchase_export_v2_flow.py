from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/purchase_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_purchase_export_navigates_to_purchase_goods_in_run_flow():
    source = _source()
    assert "await self.navigation_component.run(page, TargetPage.PURCHASE)" in source
    assert "page.goto(login_url" not in source


def test_purchase_export_searches_before_triggering_async_export():
    source = _source()
    search_index = source.index("await self._click_search(page)")
    wait_index = source.index("await self._wait_search_results_ready(page)")
    trigger_index = source.index("await self._trigger_async_export_and_download(page)")
    assert search_index < wait_index < trigger_index


def test_purchase_export_triggers_export_via_expect_download_pattern():
    """Strict mirror of orders/inventory: page.expect_download wraps the export-button click.

    Regression test for production failures efd6f74e / 188176b7 / 9575d546 where
    navigating to /purchase/export_record and polling the table failed with
    ``get_by_text("导出记录") 15000ms timeout``.

    New design asserts the strict call sequence (NO close_progress_dialog inside
    expect_download context, matching orders_export_base / inventory_export):
      open_dropdown → click_export_all_results → expect_download → click_export_button_in_dialog
    """
    source = _source()

    open_dropdown = source.index("await self._open_import_export_dropdown(page)")
    select_all_results = source.index("await self._click_export_all_results(page)")
    expect_download = source.index("async with page.expect_download(")
    click_export = source.index("await self._click_export_button_in_dialog(page)")

    # Strict mirror of orders/inventory: expect_download wraps ONLY the click that
    # triggers the export; no _close_progress_dialog or any other page interaction
    # inside the context (download event is independent of UI state).
    assert open_dropdown < select_all_results < expect_download < click_export

    # _close_progress_dialog must not be called inside the expect_download block.
    expect_block = source[expect_download:]
    expect_end = expect_block.index("download = await dl_info.value")
    inside_expect = expect_block[:expect_end]
    assert "_close_progress_dialog" not in inside_expect, (
        "_close_progress_dialog must NOT be called inside expect_download context "
        "(mirror orders/inventory: download event fires independently of UI state)"
    )


def test_purchase_export_uses_miaoshou_date_picker_for_create_date():
    source = _source()
    assert "MiaoshouDatePicker" in source
    assert "apply_custom_range(" in source
    assert "MiaoshouCustomDateRange(" in source


def test_purchase_export_uses_export_record_poll_timeout_as_download_timeout():
    """Reuses ``export_record_poll_timeout_s`` (300s) as the page.expect_download timeout.

    The selector field was originally for polling /purchase/export_record table.
    After the refactor (expect_download pattern, no nav+poll), the SAME semantic
    "max wait time for export to be downloadable" still applies, so we reuse the
    existing selector as the expect_download timeout (multiplied by 1000 for ms).
    """
    source = _source()
    assert "export_record_poll_timeout_s" in source, (
        "export_record_poll_timeout_s selector must be reused as expect_download timeout"
    )
    assert "export_record_poll_timeout_s * 1000" in source, (
        "must multiply by 1000 to convert seconds to ms for expect_download timeout"
    )
    # No more interval-based polling (no asyncio.sleep, no reload loop).
    assert "asyncio.sleep(interval_s)" not in source, (
        "polling removed — no asyncio.sleep(interval_s) loop"
    )


def test_purchase_export_uses_role_based_trigger_for_import_export_dropdown():
    source = _source()
    assert 'page.get_by_role("button", name="导入/导出")' in source
    assert 'page.get_by_role("menuitem", name="导出全部搜索结果")' in source


def test_purchase_export_uses_unified_popup_close_not_keyboard_escape():
    source = _source()
    assert "_ensure_popup_closed" in source
    assert 'page.keyboard.press("Escape")' not in source


def test_purchase_export_uses_build_standard_output_root_and_build_filename():
    source = _source()
    assert "build_standard_output_root(self.ctx, data_type=\"purchase\", granularity=\"manual\")" in source
    assert "build_filename(" in source
