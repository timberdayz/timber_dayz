"""妙手库存导出组件的行为测试。

对齐上游 spec 2026-09-13 §7「mock page 注入，验证步骤调用序列与 ExportResult 形状」。

做法：用**替身组件/替身方法**替换导出流程里的协作组件与各步骤方法，把调用记进
共享的 `calls` 列表；断言的是**运行时的调用顺序与结果形状**，不是源码文本。

为什么不用源码字符串断言：源码断言只会因为「代码被重排」而红，却抓不到
「真实运行时行为变了」——spec §2.8 记录的正是这个失效模式。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from miaoshou_page_fakes import FakePage
from modules.components.base import ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_export import (
    MiaoshouInventoryExport,
)


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def _component(calls: list[str]) -> MiaoshouInventoryExport:
    """把各协作组件与步骤方法替换为替身，记录调用序列。"""
    component = MiaoshouInventoryExport(_ctx())

    async def _nav(page, target):
        calls.append("navigation")
        return ResultBase(success=True, message="ok")

    async def _filters(page, filters):
        calls.append("warehouse_filters")
        return ResultBase(success=True, message="ok")

    async def _search(page):
        calls.append("search")

    async def _results(page):
        calls.append("search_results")

    async def _open_dialog(page):
        calls.append("open_export_dialog")

    async def _fields(page):
        calls.append("ensure_export_fields")

    async def _download(page):
        calls.append("expect_download")
        return object()

    async def _save(page, download):
        calls.append("save_download")
        return Path("inventory_snapshot.xlsx")

    component.navigation_component.run = _nav
    component.warehouse_filters_component.run = _filters
    component._click_search = _search
    component._wait_search_results_ready = _results
    component._open_export_dialog = _open_dialog
    component._ensure_export_fields_all_selected = _fields
    component._expect_download_with_pageerror_guard = _download
    component._wait_download_complete = _save
    return component


@pytest.mark.asyncio
async def test_inventory_export_calls_stages_in_expected_order() -> None:
    calls: list[str] = []
    component = _component(calls)

    result = await component.run(FakePage())

    assert result.success is True
    assert (result.file_path or "").endswith("inventory_snapshot.xlsx")
    assert calls == [
        "navigation",
        "warehouse_filters",
        "search",
        "search_results",
        "open_export_dialog",
        "ensure_export_fields",
        "expect_download",
        "save_download",
    ]


@pytest.mark.asyncio
async def test_inventory_export_does_not_use_keyboard_escape_to_close_popups() -> None:
    """关弹窗必须走统一的弹窗清理，不能用键盘 Escape 糊弄。"""
    calls: list[str] = []
    component = _component(calls)
    page = FakePage()

    await component.run(page)

    assert "Escape" not in page.keyboard.pressed
