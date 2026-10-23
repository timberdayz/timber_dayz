"""妙手库存导出组件的行为测试。

对齐上游 spec 2026-09-13 §7「mock page 注入，验证步骤调用序列与 ExportResult 形状」。

做法：用**替身组件/替身方法**替换导出流程里的协作组件与各步骤方法，把调用记进
共享的 `calls` 列表；断言的是**运行时的调用顺序与结果形状**，不是源码文本。

为什么不用源码字符串断言：源码断言只会因为「代码被重排」而红，却抓不到
「真实运行时行为变了」——spec §2.8 记录的正是这个失效模式。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from miaoshou_page_fakes import (
    FakeDownload,
    FakeDownloadPage,
    FakeLocator,
    FakePage,
)
from modules.components.base import ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
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


@pytest.mark.asyncio
async def test_inventory_export_reports_navigation_failure_with_stage_name() -> None:
    """导航失败必须带阶段名，且不得继续往下走搜索。"""
    calls: list[str] = []
    component = _component(calls)

    async def _failed_navigation(page, target):
        calls.append("navigation")
        return ResultBase(success=False, message="导航超时")

    component.navigation_component.run = _failed_navigation

    result = await component.run(FakePage())

    assert result.success is False
    assert "navigation_failed" in (result.message or "")
    assert "search" not in calls


@pytest.mark.asyncio
async def test_inventory_export_reports_warehouse_scope_failure_with_stage_name() -> (
    None
):
    """仓库范围筛选失败必须带阶段名，且不得继续往下走搜索。"""
    calls: list[str] = []
    component = _component(calls)

    async def _failed_filters(page, filters):
        calls.append("warehouse_filters")
        return ResultBase(success=False, message="warehouse_scope_open_failed: 打不开")

    component.warehouse_filters_component.run = _failed_filters

    result = await component.run(FakePage())

    assert result.success is False
    assert "warehouse_scope_failed" in (result.message or "")
    assert "search" not in calls


# ── L2-4 结构化错误（《规范》§3.5.1）────────────────────────────────────


@pytest.mark.asyncio
async def test_inventory_export_failure_message_carries_structured_fields() -> None:
    """阶段失败消息必须带上结构化字段，且既有失败前缀保持不变。"""
    component = _component([])
    page = FakePage(url="https://erp.91miaoshou.com/warehouse/checklist")

    async def _failed_navigation(page, target):
        return ResultBase(success=False, message="仓库清单标题未出现")

    component.navigation_component.run = _failed_navigation

    result = await component.run(page)
    message = result.message or ""

    assert result.success is False
    assert "navigation_failed" in message
    assert "stage=navigation_ready" in message
    assert "status=failed" in message
    assert "reason=仓库清单标题未出现" in message
    assert "current_url=https://erp.91miaoshou.com/warehouse/checklist" in message
    assert "matched_signal=warehouse_checklist_route" in message
    assert "screenshot_path=" in message


@pytest.mark.asyncio
async def test_inventory_export_failure_message_reports_screenshot_path(
    tmp_path: Path,
) -> None:
    """阶段失败时截图必须落盘，且路径出现在结构化字段里。"""
    ctx = ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={"task": {"screenshot_dir": str(tmp_path)}},
    )
    component = MiaoshouInventoryExport(ctx)
    page = FakePage(url="https://erp.91miaoshou.com/warehouse/checklist")

    async def _failed_navigation(page, target):
        return ResultBase(success=False, message="路由未切换")

    component.navigation_component.run = _failed_navigation

    result = await component.run(page)
    message = result.message or ""

    assert result.success is False
    assert page.screenshots, "阶段失败必须落盘一张截图"
    assert str(tmp_path) in message
    assert "screenshot_path=" in message


@pytest.mark.asyncio
async def test_inventory_export_download_failure_carries_stage_fields() -> None:
    """下载阶段失败同样要带结构化字段（阶段名 / 定位信号）。"""
    component = _component([])
    page = FakePage(url="https://erp.91miaoshou.com/warehouse/checklist")

    async def _failed_download(page):
        raise RuntimeError("export aborted by pageerror: filename='x.js'")

    component._expect_download_with_pageerror_guard = _failed_download

    result = await component.run(page)
    message = result.message or ""

    assert result.success is False
    assert "download_failed" in message
    assert "stage=download_saved" in message
    assert "matched_signal=page.expect_download" in message
    assert "reason=export aborted by pageerror" in message


# ── L2-8 pageerror 竞速守卫 ────────────────────────────────────────────


class _FakeJsError:
    """Playwright JSError 形状的替身。"""

    name = "TypeError"
    message = "undefined"
    stack = "TypeError: undefined\n    at handler (https://erp.91miaoshou.com/x.js:1:1)"
    filename = "https://erp.91miaoshou.com/warehouse/checklist"
    lineno = 123
    colno = 45

    def __str__(self) -> str:
        return f"{self.name}: {self.message}"


@pytest.mark.asyncio
async def test_pageerror_guard_raises_with_js_error_details() -> None:
    """pageerror 先到：抛 RuntimeError，且消息含 filename/lineno/colno/name/stack。"""
    component = MiaoshouInventoryExport(_ctx())
    page = FakeDownloadPage(url="https://erp.91miaoshou.com/warehouse/checklist")

    async def _trigger(page):
        page.emit_pageerror(_FakeJsError())
        await asyncio.sleep(0)

    component._trigger_export = _trigger

    with pytest.raises(RuntimeError) as excinfo:
        await component._expect_download_with_pageerror_guard(page)

    message = str(excinfo.value)
    assert "export aborted by pageerror" in message
    assert "filename='https://erp.91miaoshou.com/warehouse/checklist'" in message
    assert "lineno=123" in message
    assert "colno=45" in message
    assert "name='TypeError'" in message
    assert "stack=" in message


@pytest.mark.asyncio
async def test_pageerror_guard_returns_download_when_download_wins() -> None:
    """download 先到：正常返回下载对象，并清理 pageerror listener。"""
    component = MiaoshouInventoryExport(_ctx())
    download = FakeDownload()
    page = FakeDownloadPage(
        download=download, url="https://erp.91miaoshou.com/warehouse/checklist"
    )

    async def _trigger(page):
        await asyncio.sleep(0)

    component._trigger_export = _trigger

    result = await component._expect_download_with_pageerror_guard(page)

    assert result is download
    assert "pageerror" not in page.handlers


# ── L2-7 假配置接上 ───────────────────────────────────────────────────


def _dialog_locator(
    *,
    group_titles: tuple[str, ...],
    check_all_text: str,
    checked: bool = True,
    second_checked: bool = True,
) -> tuple[FakeLocator, FakeLocator]:
    """构造「选择导出字段」弹窗替身。

    返回 (弹窗, 第二个分组的「全选」复选框)；复选框集合用 nth_children
    表达「第一个 / 第二个」的语义。
    """
    first_box = FakeLocator(checked=checked, evaluate_checked=checked)
    second_box = FakeLocator(checked=second_checked, evaluate_checked=second_checked)
    box_collection = FakeLocator(
        count=2,
        checked=checked,
        evaluate_checked=checked,
        nth_children={0: first_box, 1: second_box},
    )
    children: dict[str, Any] = {f"role:checkbox:{check_all_text}": box_collection}
    for title in group_titles:
        children[f"text:{title}"] = FakeLocator()
    children[f"text:{check_all_text}"] = FakeLocator()
    dialog = FakeLocator(children=children)
    # 旧实现会把 dialog.locator("xpath=.") 传给下层步骤，这里给出等价对象，
    # 保证「是否重新定位弹窗」成为唯一变量。
    dialog.children["xpath=."] = dialog
    return dialog, second_box


@pytest.mark.asyncio
async def test_export_fields_use_configured_group_titles_and_check_all_text() -> None:
    """分组标题与「全选」文案必须来自 InventorySelectors，而不是硬编码字面量。"""
    selectors = InventorySelectors(
        group_titles=("字段组甲",),
        group_check_all_text="全部勾选",
    )
    component = MiaoshouInventoryExport(_ctx(), selectors=selectors)
    dialog, second_box = _dialog_locator(
        group_titles=("字段组甲",),
        check_all_text="全部勾选",
        checked=True,
        second_checked=False,
    )
    legacy_title = FakeLocator()
    legacy_box = FakeLocator(count=2, checked=True, evaluate_checked=True)
    page = FakePage(
        locators={
            "role:dialog:None": dialog,
            "text:商品信息": legacy_title,
            "text:其他信息": legacy_title,
            "role:checkbox:全选": legacy_box,
        }
    )

    await component._ensure_export_fields_all_selected(page)

    assert dialog.children["text:字段组甲"].wait_calls, "必须等待配置里的分组标题"
    assert legacy_title.wait_calls == [], "不得再等待硬编码的分组标题"
    assert legacy_box.wait_calls == [], "不得再使用硬编码的「全选」文案"
    assert second_box.clicked == 1


@pytest.mark.asyncio
async def test_wait_download_complete_uses_configured_data_type_dir(
    tmp_path: Path,
) -> None:
    """落盘目录必须用 InventorySelectors.data_type_dir，而不是硬编码 inventory。"""
    selectors = InventorySelectors(data_type_dir="inv_snapshot")
    ctx = ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={"download_dir": str(tmp_path), "shop_name": "shop"},
    )
    component = MiaoshouInventoryExport(ctx, selectors=selectors)
    download = FakeDownload(suggested_filename="inv.xlsx")

    target = await component._wait_download_complete(FakePage(), download)

    assert "inv_snapshot" in str(target)
    assert target.exists()


# ── L2-9 动态 DOM：关键交互前重新定位 ─────────────────────────────────


class _RotatingDialogPage(FakePage):
    """每次取 dialog 都返回一个新的弹窗对象（模拟弹窗被重渲染）。"""

    def __init__(self, dialogs: list[FakeLocator]) -> None:
        super().__init__()
        self._dialogs = list(dialogs)
        self.dialog_queries = 0

    def get_by_role(self, role: str, name: Any = None) -> Any:
        if role == "dialog" and name is None:
            index = min(self.dialog_queries, len(self._dialogs) - 1)
            self.dialog_queries += 1
            return self._dialogs[index]
        return super().get_by_role(role, name)


@pytest.mark.asyncio
async def test_export_fields_relocate_dialog_before_second_checkbox() -> None:
    """第二个分组的「全选」必须作用在**重新定位**后的弹窗上。"""
    first_dialog, first_second = _dialog_locator(
        group_titles=("商品信息", "其他信息"),
        check_all_text="全选",
        checked=True,
        second_checked=False,
    )
    second_dialog, second_second = _dialog_locator(
        group_titles=("商品信息", "其他信息"),
        check_all_text="全选",
        checked=True,
        second_checked=False,
    )
    page = _RotatingDialogPage([first_dialog, second_dialog])
    component = MiaoshouInventoryExport(_ctx())

    await component._ensure_export_fields_all_selected(page)

    assert page.dialog_queries >= 2, "关键交互前必须重新定位弹窗"
    assert second_second.clicked == 1, "第二个分组的全选必须点在重新定位后的弹窗上"
    assert first_second.clicked == 0, "不得使用旧的（已失效的）弹窗 locator"


@pytest.mark.asyncio
async def test_open_export_dialog_clicks_menu_button_and_item() -> None:
    """打开导出菜单：点「导入/导出商品」→ 点「导出搜索的商品」→ 等弹窗可见。"""
    menu_button = FakeLocator()
    menu_item = FakeLocator()
    page = FakePage(
        locators={
            "role:button:导入/导出商品": menu_button,
            "role:menuitem:导出搜索的商品": menu_item,
            "role:dialog:None": FakeLocator(),
        }
    )
    component = MiaoshouInventoryExport(_ctx())

    await component._open_export_dialog(page)

    assert menu_button.clicked == 1
    assert menu_item.clicked == 1


@pytest.mark.asyncio
async def test_trigger_export_clicks_configured_export_button() -> None:
    """触发导出：重新定位弹窗后点配置里的导出按钮。"""
    export_button = FakeLocator()
    dialog = FakeLocator(children={"button:has-text(导出)": export_button})
    page = FakePage(locators={"role:dialog:None": dialog})
    component = MiaoshouInventoryExport(_ctx())

    await component._trigger_export(page)

    assert export_button.clicked == 1
