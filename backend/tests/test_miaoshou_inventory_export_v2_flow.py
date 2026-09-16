from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/inventory_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_inventory_export_navigates_to_warehouse_after_login():
    source = _source()
    assert "await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)" in source
    assert "page.goto(login_url" not in source


def test_inventory_export_applies_warehouse_scope_filter_before_search():
    source = _source()
    filter_index = source.index("await self.warehouse_filters_component.run(page")
    search_index = source.index("await self._click_search(page)")
    assert filter_index < search_index


def test_inventory_export_opens_export_dialog_and_selects_all_groups_before_export():
    """dialog → 字段全选 → expect_download 必须在 run() 体内按序出现。

    v4.20.0+ ID=621 修复后：``_trigger_export(page)`` 被提取到
    ``_expect_download_with_pageerror_guard`` 内（race pageerror 监听），
    所以严格按 source.index 顺序检查 ``_trigger_export`` 不再适用
    （它现在在 helper 函数体内，helper 在 run() 之前定义）。
    改为在 ``run()`` 体内检查 helper 调用顺序，并断言 ``_trigger_export``
    不在 run() 体内出现（确保它只在 helper 内被调用，pageerror guard 包裹 click）。
    """
    source = _source()
    # 提取 run() 函数体（在 "async def run" 之后到下一个 "async def " 或 "def " 之前）
    run_start = source.index("async def run(self")
    next_def = source.find("\n    async def ", run_start + 1)
    next_def2 = source.find("\n    def ", run_start + 1)
    next_def = min(
        pos for pos in (next_def, next_def2, len(source)) if pos > run_start
    )
    run_body = source[run_start:next_def]
    open_dialog = run_body.index("await self._open_export_dialog(page)")
    ensure_fields = run_body.index("await self._ensure_export_fields_all_selected(page)")
    helper_call = run_body.index("await self._expect_download_with_pageerror_guard(page)")
    assert open_dialog < ensure_fields < helper_call, (
        "run() 体内顺序必须是: open_dialog → ensure_fields → expect_download guard"
    )
    # _trigger_export 不应在 run() 体内出现（必须包裹在 helper 内，确保 pageerror guard）
    assert "await self._trigger_export(page)" not in run_body, (
        "_trigger_export(page) 不能直接出现在 run() 顶层 — "
        "必须包裹在 _expect_download_with_pageerror_guard 内以保证 pageerror guard"
    )


def test_inventory_export_treats_progress_as_intermediate_and_download_as_final_signal():
    source = _source()
    assert "await self._wait_export_progress_ready(page)" in source
    assert "async with page.expect_download(" in source
    assert "if not tmp_path.exists() or tmp_path.stat().st_size <= 0" in source


def test_inventory_export_uses_role_based_trigger_and_menuitem_for_export_dropdown():
    source = _source()
    assert 'page.get_by_role("button", name="导入/导出商品").first' in source
    assert 'page.get_by_role("menuitem", name="导出搜索的商品").first' in source


def test_inventory_export_uses_unified_popup_close_not_keyboard_escape():
    source = _source()
    assert "_ensure_popup_closed" in source
    assert 'page.keyboard.press("Escape")' not in source


def test_inventory_export_uses_build_standard_output_root_and_build_filename():
    source = _source()
    assert "build_standard_output_root(self.ctx, data_type=\"inventory\", granularity=\"snapshot\")" in source
    assert "build_filename(" in source
