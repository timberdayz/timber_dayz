"""妙手仓库清单「更新时间维度 + 区间」筛选组件的行为测试。

守的是**三条静默失败**（页面照常显示、不报错，只会安静地给错数据）：
1. 维度没切（默认「创建时间」）
2. 区间没落进去
3. 搜索没刷新 / 结果为空

真实页面结构（2026-10-26 失败现场取证）：
- 时间维度是**内联下拉**，触发器直接显示「创建时间」/「更新时间」
- 下拉浮层里就两项
- 日期区间是**内联的两个输入框**（placeholder「开始时间」「结束时间」）
- **没有「确定」「清空」按钮** —— 填完直接点「搜索」

→ 所以「页面上没有确定按钮」必须算**成功路径**，不是失败。
（旧版本把「确定」当必经步骤，页面结构一变就整段失败。）
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_date_filter import (
    DIMENSION_CREATE,
    DIMENSION_MODIFIED,
    MiaoshouInventoryDateFilter,
    assert_search_results_refreshed,
)

START = "2026-10-01 00:00:00"
END = "2026-10-25 23:59:59"


class FakeNode:
    def __init__(
        self,
        page: "FakePage",
        text: str = "",
        *,
        visible: bool = True,
        value: str = "",
        attrs: Optional[dict] = None,
    ) -> None:
        self.page = page
        self.text = text
        self.visible = visible
        self.value = value
        self.attrs = dict(attrs or {})
        self.clicks = 0

    async def is_visible(self) -> bool:
        return self.visible

    async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if not self.visible:
            raise RuntimeError("element not visible")

    async def click(self, timeout: int = 0) -> None:
        self.clicks += 1
        self.page.on_click(self)

    async def get_attribute(self, name: str) -> Optional[str]:
        if name == "value":
            return self.value
        return self.attrs.get(name)

    async def text_content(self) -> str:
        return self.text

    async def input_value(self) -> str:
        return self.value

    async def fill(self, value: str, timeout: int = 0) -> None:
        self.value = value

    async def press(self, key: str) -> None:
        return None

    def locator(self, selector: str) -> "FakeLocator":
        # 「祖先」点击等价于点自己（真实页面里点祖先会冒泡到触发器）
        if selector.startswith("xpath=ancestor"):
            return FakeLocator(self.page, [self])
        return FakeLocator(self.page, [])


class FakeLocator:
    def __init__(self, page: "FakePage", nodes: list[FakeNode]) -> None:
        self.page = page
        self.nodes = nodes

    @property
    def first(self) -> FakeNode:
        return self.nodes[0] if self.nodes else FakeNode(self.page, visible=False)

    def nth(self, index: int) -> FakeNode:
        if index < len(self.nodes):
            return self.nodes[index]
        return FakeNode(self.page, visible=False)

    async def count(self) -> int:
        return len(self.nodes)


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    async def press(self, key: str) -> None:
        if key == "Escape":
            self.page.dropdown_open = False


class FakePage:
    """按真实页面结构分派的假页面。"""

    def __init__(
        self,
        *,
        dimension: str = DIMENSION_CREATE,
        modified_option_present: bool = True,
        dimension_takes_effect: bool = True,
        range_input_count: int = 2,
        confirm_present: bool = False,
        fill_takes_effect: bool = True,
        sku_total_text: str = "SKU总数：1113",
    ) -> None:
        self.dimension = dimension
        self.modified_option_present = modified_option_present
        self.dimension_takes_effect = dimension_takes_effect
        self.fill_takes_effect = fill_takes_effect
        self.dropdown_open = False

        self.trigger_node = FakeNode(self, text=dimension)
        self.option_create = FakeNode(self, text=DIMENSION_CREATE)
        self.option_modified = FakeNode(self, text=DIMENSION_MODIFIED)
        self.start_input = FakeNode(self)
        self.end_input = FakeNode(self)
        self.confirm_node = FakeNode(self)
        self.root_node = FakeNode(self, attrs={"modelvaluegroup": ""})
        self.sku_node = FakeNode(self, text=sku_total_text)

        self.range_inputs = [self.start_input, self.end_input][:range_input_count]
        self.confirm_present = confirm_present

    # -- 交互副作用 ----------------------------------------------------
    def on_click(self, node: FakeNode) -> None:
        if node is self.trigger_node:
            self.dropdown_open = True
            return
        if node is self.option_modified:
            if self.dimension_takes_effect:
                self.dimension = DIMENSION_MODIFIED
                self.trigger_node.text = DIMENSION_MODIFIED
            self.dropdown_open = False
            return
        if node is self.option_create:
            self.dropdown_open = False
            return
        if node is self.confirm_node:
            return

    # -- Playwright 表面 ------------------------------------------------
    def locator(self, selector: str) -> FakeLocator:
        if "placeholder*='开始时间'" in selector:
            return FakeLocator(self, [self.start_input] if self.range_inputs else [])
        if "placeholder*='结束时间'" in selector:
            return FakeLocator(self, [self.end_input] if self.range_inputs else [])
        if "jx-range-input" in selector:
            return FakeLocator(self, list(self.range_inputs))
        if "is-plain" in selector:
            return FakeLocator(
                self, [self.confirm_node] if self.confirm_present else []
            )
        if selector.startswith("[data-field="):
            return FakeLocator(self, [self.root_node])
        return FakeLocator(self, [])

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        if text in (DIMENSION_CREATE, DIMENSION_MODIFIED):
            nodes: list[FakeNode] = []
            if self.trigger_node.text == text:
                nodes.append(self.trigger_node)
            if self.dropdown_open:
                if self.option_create.text == text:
                    nodes.append(self.option_create)
                if self.modified_option_present and self.option_modified.text == text:
                    nodes.append(self.option_modified)
            return FakeLocator(self, nodes)
        if text == "SKU总数":
            return FakeLocator(self, [self.sku_node])
        return FakeLocator(self, [])

    @property
    def keyboard(self) -> FakeKeyboard:
        return FakeKeyboard(self)

    async def wait_for_timeout(self, ms: int) -> None:
        return None


def _component() -> MiaoshouInventoryDateFilter:
    return MiaoshouInventoryDateFilter(ctx=None, selectors=InventorySelectors())


@pytest.mark.asyncio
async def test_applies_modified_dimension_and_range_without_confirm_button():
    """真实页面没有「确定/清空」按钮 —— 整段流程必须能走通。"""
    page = FakePage(confirm_present=False)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension == DIMENSION_MODIFIED
    assert evidence.dimension_is_modified
    assert START.split(" ")[0] in evidence.applied_range
    assert END.split(" ")[0] in evidence.applied_range
    assert page.start_input.value == START
    assert page.end_input.value == END


@pytest.mark.asyncio
async def test_skips_dimension_switch_when_already_modified():
    """已经是「更新时间」→ 幂等，不该再去点下拉（用户可能已手动选过）。"""
    page = FakePage(dimension=DIMENSION_MODIFIED)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension == DIMENSION_MODIFIED
    assert page.option_modified.clicks == 0


@pytest.mark.asyncio
async def test_reads_current_dimension_from_trigger_not_dropdown_option():
    """浮层开着时读到的必须是**触发器**上的当前值，不是浮层里的选项。"""
    page = FakePage(dimension=DIMENSION_CREATE)
    component = _component()

    # 模拟「用户已经打开了下拉但还没选」
    page.dropdown_open = True

    assert await component.read_current_dimension(page) == DIMENSION_CREATE


@pytest.mark.asyncio
async def test_fails_when_modified_option_is_missing():
    """维度下拉里没有「更新时间」→ 必须失败，不能默默采成「创建时间」。"""
    page = FakePage(modified_option_present=False)

    with pytest.raises(RuntimeError, match="更新时间"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_dimension_switch_does_not_take_effect():
    """点了「更新时间」但触发器文案没变 → 必须失败（静默失败 #1）。"""
    page = FakePage(dimension_takes_effect=False)

    with pytest.raises(RuntimeError, match="维度未切到"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_range_inputs_are_missing():
    """找不到「开始时间/结束时间」输入框 → 必须失败（否则导出的是全量）。"""
    page = FakePage(range_input_count=0)

    with pytest.raises(RuntimeError, match="找不到日期区间输入框"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_range_is_not_applied():
    """区间没落进去 → 必须失败（静默失败 #2）。"""
    page = FakePage(fill_takes_effect=False)

    async def _no_fill(value: str, timeout: int = 0) -> None:
        return None

    for node in (page.start_input, page.end_input):
        node.fill = _no_fill  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="区间未生效"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_clicks_confirm_when_page_does_have_it():
    """页面**有**「确定」按钮时要点它（老版页面的兼容路径）。"""
    page = FakePage(confirm_present=True)

    await _component().apply_incremental_range(page, start=START, end=END)

    assert page.confirm_node.clicks == 1


@pytest.mark.asyncio
async def test_reads_sku_total():
    page = FakePage(sku_total_text="SKU总数：11003 库存总价值（元）：223561.83")

    assert await _component().read_sku_total(page) == 11003


def test_assert_search_results_refreshed_rejects_growth():
    with pytest.raises(RuntimeError, match="反而变多"):
        assert_search_results_refreshed(total_before=100, total_after=200)


def test_assert_search_results_refreshed_rejects_empty():
    with pytest.raises(RuntimeError, match="SKU总数"):
        assert_search_results_refreshed(total_before=100, total_after=0)


def test_assert_search_results_refreshed_accepts_equal_with_warning():
    """筛选前后相等（长窗口覆盖全量）→ 只警告，不报错。"""
    assert_search_results_refreshed(total_before=100, total_after=100)
