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


def test_purchase_export_triggers_export_then_polls_export_record_then_downloads():
    source = _source()

    open_dropdown = source.index("await self._open_import_export_dropdown(page)")
    select_all_results = source.index("await self._click_export_all_results(page)")
    close_progress = source.index("await self._close_progress_dialog(page)")
    nav_record = source.index("await self._navigate_to_export_record(page)")
    poll_record = source.index("await self._poll_export_record_until_ready(page)")
    expect_download = source.index("async with page.expect_download(")

    assert open_dropdown < select_all_results < close_progress < nav_record < poll_record < expect_download


def test_purchase_export_uses_miaoshou_date_picker_for_create_date():
    source = _source()
    assert "MiaoshouDatePicker" in source
    assert "apply_custom_range(" in source
    assert "MiaoshouCustomDateRange(" in source


def test_purchase_export_polls_export_record_with_timeout_and_interval():
    source = _source()
    assert "export_record_poll_timeout_s" in source
    assert "export_record_poll_interval_s" in source
    assert "await asyncio.sleep(interval_s)" in source


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
