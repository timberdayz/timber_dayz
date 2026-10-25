"""妙手仓库清单「更新时间维度 + 区间」筛选组件的行为测试。

守的是**三条静默失败**（页面照常显示、不报错，只会安静地给错数据）：
1. 维度没切（默认「创建时间」）
2. 「确定」没点（区间填了没提交）
3. 搜索没刷新 / 结果为空

另加一条防呆：「确定」与「清空」class 相近，必须用完整 class 区分。
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_date_filter import (
    MiaoshouInventoryDateFilter,
    assert_search_results_refreshed,
)

START = "2026-10-01 00:00:00"
END = "2026-10-25 23:59:59"


class FakeNode:
    def __init__(self, page: "FakePage", attrs=None, text: str = "") -> None:
        self.page = page
        self.attrs = dict(attrs or {})
        self.text = text
        self.visible = True
        self.value = ""
        self.clicks = 0

    async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if not self.visible:
            raise RuntimeError("element not visible")

    async def click(self, timeout: int = 0) -> None:
        self.clicks += 1
        self.page.on_click(self)

    async def get_attribute(self, name: str) -> Optional[str]:
        return self.attrs.get(name)

    async def text_content(self) -> str:
        return self.text

    async def fill(self, value: str, timeout: int = 0) -> None:
        self.value = value

    async def press(self, key: str) -> None:
        return None

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self.page, [])


class FakeLocator:
    def __init__(self, page: "FakePage", nodes: list[FakeNode]) -> None:
        self.page = page
        self.nodes = nodes

    @property
    def first(self) -> FakeNode:
        return self.nodes[0] if self.nodes else FakeNode(self.page)

    def nth(self, index: int) -> FakeNode:
        if index < len(self.nodes):
            return self.nodes[index]
        return FakeNode(self.page)

    async def count(self) -> int:
        return len(self.nodes)


class FakePage:
    """按选择器分派的假页面。"""

    def __init__(
        self,
        *,
        dimension: str = "gmtCreate",
        applied_range: str = "",
        confirm_applies: bool = True,
        dimension_takes_effect: bool = True,
        modified_option_present: bool = True,
        range_input_count: int = 2,
        sku_total_text: str = "SKU总数：1113",
    ) -> None:
        self.dimension = dimension
        self.confirm_applies = confirm_applies
        self.dimension_takes_effect = dimension_takes_effect
        self.modified_option_present = modified_option_present
        self.range_input_count = range_input_count
        self.sku_total_text = sku_total_text

        self.dimension_node = FakeNode(self, attrs={"modelvaluegroup": dimension})
        self.root_node = FakeNode(self, attrs={"modelvaluegroup": applied_range})
        self.wrapper_node = FakeNode(self)
        self.panel_node = FakeNode(self)
        self.confirm_node = FakeNode(self)
        self.clear_node = FakeNode(self)
        self.range_inputs = [FakeNode(self), FakeNode(self)][:range_input_count]
        self.options = [FakeNode(self, text="创建时间")]
        if modified_option_present:
            self.options.append(FakeNode(self, text="更新时间"))

    # -- 交互副作用 ----------------------------------------------------
    def on_click(self, node: FakeNode) -> None:
        if node is self.dimension_node or node is self.wrapper_node:
            return
        if node in self.options:
            if "更新时间" in node.text and self.dimension_takes_effect:
                self.dimension_node.attrs["modelvaluegroup"] = "gmtModified"
            return
        if node is self.confirm_node:
            if not self.confirm_applies:
                return
            values = [item.value for item in self.range_inputs]
            if len(values) >= 2 and values[0] and values[1]:
                self.root_node.attrs["modelvaluegroup"] = f"{values[0]},{values[1]}"
            return
        if node is self.clear_node:
            self.root_node.attrs["modelvaluegroup"] = ""

    # -- Playwright 表面 ------------------------------------------------
    def locator(self, selector: str) -> FakeLocator:
        if selector == ".jx-picker-panel":
            return FakeLocator(self, [self.panel_node])
        if selector == ".jx-picker-panel .jx-select":
            return FakeLocator(self, [self.dimension_node])
        if selector == ".jx-picker-panel .jx-select__wrapper":
            return FakeLocator(self, [self.wrapper_node])
        if selector == ".jx-picker-panel .jx-select-dropdown li":
            return FakeLocator(self, list(self.options))
        if selector == ".jx-picker-panel input.jx-range-input":
            return FakeLocator(self, list(self.range_inputs))
        if selector == "button.jx-picker-panel__link-btn.is-plain":
            return FakeLocator(self, [self.confirm_node])
        if selector == "button.jx-picker-panel__link-btn.is-text":
            return FakeLocator(self, [self.clear_node])
        if selector.startswith("[data-field="):
            return FakeLocator(self, [self.root_node])
        return FakeLocator(self, [])

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        if text == "SKU总数":
            return FakeLocator(self, [FakeNode(self, text=self.sku_total_text)])
        return FakeLocator(self, [])

    async def wait_for_timeout(self, ms: int) -> None:
        return None


def _component() -> MiaoshouInventoryDateFilter:
    return MiaoshouInventoryDateFilter(ctx=None, selectors=InventorySelectors())


@pytest.mark.asyncio
async def test_applies_modified_dimension_and_range():
    page = FakePage()

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension.startswith("gmtModified")
    assert START.split(" ")[0] in evidence.applied_range
    assert END.split(" ")[0] in evidence.applied_range
    # 「确定」必须真的被点了（不是「清空」）
    assert page.confirm_node.clicks == 1
    assert page.clear_node.clicks == 0


@pytest.mark.asyncio
async def test_fails_when_modified_dimension_option_is_missing():
    """维度下拉里没有「更新时间」→ 必须失败，不能默默采成「创建时间」。"""
    page = FakePage(modified_option_present=False)

    with pytest.raises(RuntimeError, match="维度下拉里找不到"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_dimension_switch_does_not_take_effect():
    """点了「更新时间」但 modelvaluegroup 没变 → 必须失败（静默失败 #1）。"""
    page = FakePage(dimension_takes_effect=False)

    with pytest.raises(RuntimeError, match="维度未切到"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_range_is_not_applied_after_confirm():
    """「确定」没点 → 筛选器还是旧值 → 必须失败（静默失败 #2）。"""
    page = FakePage(confirm_applies=False)

    with pytest.raises(RuntimeError, match="区间未生效"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_range_inputs_are_missing():
    page = FakePage(range_input_count=1)

    with pytest.raises(RuntimeError, match="日期区间输入框不足两个"):
        await _component().apply_incremental_range(page, start=START, end=END)


def test_confirm_and_clear_buttons_use_different_full_class():
    """「确定」与「清空」必须用**完整 class** 区分，否则会误点「清空」。"""
    selectors = InventorySelectors()

    assert "is-plain" in selectors.inventory_date_filter_confirm_selector
    assert "is-text" in selectors.inventory_date_filter_clear_selector
    assert (
        selectors.inventory_date_filter_confirm_selector
        != selectors.inventory_date_filter_clear_selector
    )


@pytest.mark.asyncio
async def test_read_sku_total_returns_the_number():
    page = FakePage(sku_total_text="SKU总数：1,113")
    component = _component()

    assert await component.read_sku_total(page) == 1113


@pytest.mark.asyncio
async def test_read_sku_total_is_none_when_the_text_is_missing():
    page = FakePage(sku_total_text="没有计数")

    assert await _component().read_sku_total(page) is None


def test_search_refresh_assertion_rejects_empty_and_growing_results():
    with pytest.raises(RuntimeError, match="SKU总数"):
        assert_search_results_refreshed(total_before=1113, total_after=0)

    with pytest.raises(RuntimeError, match="反而变多"):
        assert_search_results_refreshed(total_before=1113, total_after=2000)

    with pytest.raises(RuntimeError, match="没有刷新"):
        assert_search_results_refreshed(total_before=1113, total_after=None)


def test_search_refresh_assertion_accepts_narrowed_results():
    """筛选后变少 = 正常。"""
    assert_search_results_refreshed(total_before=1113, total_after=147)


def test_search_refresh_assertion_only_warns_when_counts_are_equal():
    """相等只记警告：增量窗口可能覆盖了全量数据，此时相等是合法的。"""
    messages: list[str] = []

    class _Logger:
        def warning(self, message: str) -> None:
            messages.append(message)

    assert_search_results_refreshed(
        total_before=1113, total_after=1113, logger=_Logger()
    )

    assert messages, "相等时应该留一条警告日志"
