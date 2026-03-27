from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/orders_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_orders_export_navigates_to_orders_detail_url_in_run_flow():
    source = _source()

    assert "_orders_detail_url(" in source
    assert "page.goto(" in source


def test_orders_export_searches_before_export_menu_and_download():
    source = _source()

    search_index = source.index("await self._click_search(page)")
    wait_index = source.index("await self._wait_search_results_ready(page)")
    menu_index = source.index("await self._ensure_export_menu_open(page)")
    download_index = source.index("async with page.context.expect_download(")

    assert search_index < wait_index < menu_index < download_index


def test_orders_export_uses_unified_time_selection_without_legacy_date_preset_fallback():
    source = _source()

    assert 'time_selection = cfg.get("time_selection") or {}' in source
    assert 'cfg.get("date_preset")' not in source


def test_orders_export_treats_progress_as_intermediate_and_file_as_final_signal():
    source = _source()

    assert "await self._wait_export_progress_ready(page)" in source
    assert "if not tmp_path.exists() or tmp_path.stat().st_size <= 0" in source
