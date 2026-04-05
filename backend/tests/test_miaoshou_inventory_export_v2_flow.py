from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_inventory_export_navigates_to_warehouse_after_login():
    source = _source()

    assert "await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)" in source
    assert "page.goto(login_url" not in source


def test_inventory_export_applies_scope_filter_before_search():
    source = _source()

    ensure_scope = source.index("await self._ensure_scope_filter_all_selected(page)")
    click_search = source.index("await self._click_search(page)")

    assert ensure_scope < click_search


def test_inventory_export_opens_export_dialog_and_selects_all_groups_before_export():
    source = _source()

    open_dialog = source.index("await self._open_export_dialog(page)")
    ensure_fields = source.index("await self._ensure_export_fields_all_selected(page)")
    trigger_export = source.index("await self._trigger_export(page)")

    assert open_dialog < ensure_fields < trigger_export


def test_inventory_export_treats_progress_as_intermediate_and_download_as_final_signal():
    source = _source()

    assert "await self._wait_export_progress_ready(page)" in source
    assert "async with page.expect_download(" in source
    assert "if not tmp_path.exists() or tmp_path.stat().st_size <= 0" in source


def test_inventory_export_uses_role_based_trigger_and_menuitem_for_export_dropdown():
    source = _source()

    assert 'page.get_by_role("button", name="导入/导出商品").first' in source
    assert 'page.get_by_role("menuitem", name="导出搜索的商品").first' in source


def test_inventory_export_scopes_field_selection_to_visible_dialog_root_instead_of_title_ancestor():
    source = _source()

    assert 'locator("xpath=ancestor::*[contains(@class,\'dialog\') or @role=\'dialog\' or contains(@class,\'modal\')][1]")' not in source
    assert 'dialog.get_by_text("商品信息", exact=False).first' in source
    assert 'dialog.get_by_text("其他信息", exact=False).first' in source
    assert 'dialog.get_by_role("checkbox", name="全选")' in source
