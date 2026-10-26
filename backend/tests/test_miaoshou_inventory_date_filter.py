"""妙手仓库清单「更新时间维度 + 区间」筛选组件的行为测试。

守的是**三条静默失败**（页面照常显示、不报错，只会安静地给错数据）：
1. 维度没切（默认「创建时间」）
2. 区间没落进去
3. 搜索没刷新 / 结果为空

真实页面结构（2026-10-26 两次失败现场取证）
------------------------------------------------
- 时间维度是**内联下拉**，触发器直接显示「创建时间」/「更新时间」
- 下拉浮层里就两项
- 日期区间是**内联的两个输入框**（placeholder「开始时间」「结束时间」）
- **没有「确定」「清空」按钮** —— 填完直接点「搜索」

→ 所以「页面上没有确定按钮」必须算**成功路径**，不是失败。
（旧版本把「确定」当必经步骤，页面结构一变就整段失败。）

⚠️ 表格表头里也有**一模一样的**「创建时间」「更新时间」两列。
   全页 ``get_by_text("更新时间")`` 的第一个命中是**表头**，不是下拉选项 ——
   点下去变成「按更新时间排序」，维度根本没切
   （2026-10-26 任务 5526faf9 的真实失败原因）。
   所以下面的 FakePage **刻意复刻了这个同名陷阱**。
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
        requires_open: bool = False,
        requires_panel: bool = False,
        disabled: bool = False,
    ) -> None:
        self.page = page
        self.text = text
        self.visible = visible
        self.value = value
        self.attrs = dict(attrs or {})
        self.requires_open = requires_open
        self.requires_panel = requires_panel
        self.disabled = disabled
        self.clicks = 0

    async def is_visible(self) -> bool:
        if self.requires_open and not self.page.dropdown_open:
            return False
        if self.requires_panel and not self.page.panel_open:
            return False
        return self.visible

    async def is_disabled(self) -> bool:
        return self.disabled

    async def count(self) -> int:
        return 1

    async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if not await self.is_visible():
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

    async def inner_text(self) -> str:
        return self.text

    async def input_value(self) -> str:
        return self.value

    async def fill(self, value: str, timeout: int = 0) -> None:
        self.value = value

    async def press(self, key: str) -> None:
        return None

    def locator(self, selector: str) -> "FakeLocator":
        # 「祖先」/「父节点」/「wrapper」点击等价于点自己
        # （真实页面里点祖先会冒泡到触发器）
        if selector.startswith("xpath=ancestor") or selector == "xpath=..":
            return FakeLocator(self.page, [self])
        if "wrapper" in selector:
            return FakeLocator(self.page, [self])
        return FakeLocator(self.page, [])


class FakeDropdown(FakeNode):
    """下拉浮层容器：只有打开时才可见，里面装着两个选项。"""

    def __init__(self, page: "FakePage", options: list[FakeNode]) -> None:
        super().__init__(page, visible=True, requires_open=True)
        self.options = options

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self.page, list(self.options))


class FakeConfirm(FakeNode):
    """日期面板里的「确定」。

    真实页面（2026-10-26 取证）：**fill 之后它是 disabled**（点不动），
    草稿提交（Tab 失焦）之后才变可用。
    → 「disabled」是 **「picker 还没收到值」**的信号，
      跟「页面根本没有确定按钮」是两回事，不能混为一谈。
    """

    async def is_disabled(self) -> bool:
        if self.page.confirm_enabled_at_once:
            return False
        return not self.page.range_committed


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
            was_panel_open = self.page.panel_open
            self.page.dropdown_open = False
            self.page.panel_open = False
            if was_panel_open:
                # 真实页面：Escape 会把**没提交**的值回滚掉（实测）
                self.page.start_input.value = ""
                self.page.end_input.value = ""
        elif key == "Tab":
            # 真实页面：Tab = 真实 blur → picker 收到值、「确定」变可用
            # （实测：fill + Tab 之后搜索请求里的 gmtCreateStart/End 非空）
            self.page.dropdown_open = False
            self.page.range_committed = True
            if self.page.panel_closes_on_blur:
                self.page.panel_open = False
            if self.page.rollback_on_blur:
                self.page.start_input.value = ""
                self.page.end_input.value = ""


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
        confirm_enabled_at_once: bool = False,
        panel_closes_on_blur: bool = True,
        fill_takes_effect: bool = True,
        sku_total_text: str = "SKU总数：1113",
        dimension_select_present: bool = True,
        table_header_present: bool = True,
        rollback_on_blur: bool = False,
    ) -> None:
        self.dimension = dimension
        self.modified_option_present = modified_option_present
        self.dimension_takes_effect = dimension_takes_effect
        self.fill_takes_effect = fill_takes_effect
        self.dropdown_open = False

        self._build_dimension_nodes()
        self.start_input = FakeNode(self)
        self.end_input = FakeNode(self)
        self.confirm_node = FakeConfirm(
            self, visible=confirm_present, requires_panel=True
        )
        # 日期选择面板：点开区间输入框后弹出，会挡住「搜索」按钮
        self.date_panel = FakeNode(self, requires_panel=True)
        self.root_node = FakeNode(self, attrs={"modelvaluegroup": ""})
        self.sku_node = FakeNode(self, text=sku_total_text)

        self.range_inputs = [self.start_input, self.end_input][:range_input_count]
        self.confirm_present = confirm_present
        self.dimension_select_present = dimension_select_present
        self.table_header_present = table_header_present
        self.panel_open = False
        self.rollback_on_blur = rollback_on_blur
        # 区间草稿有没有提交给 picker（提交之后「确定」才变可用）
        self.range_committed = False
        self.confirm_enabled_at_once = confirm_enabled_at_once
        self.panel_closes_on_blur = panel_closes_on_blur

    # -- 交互副作用 ----------------------------------------------------
    def _build_dimension_nodes(self) -> None:
        """维度触发器 + 表格表头的同名两列 + 下拉浮层里的选项。"""
        key = "gmtModified," if self.dimension == DIMENSION_MODIFIED else "gmtCreate,"
        self.trigger_node = FakeNode(
            self, text=self.dimension, attrs={"modelvaluegroup": key}
        )
        # 表格表头里的同名两列（**真实页面上它们排在浮层之前**）
        self.header_create = FakeNode(self, text=DIMENSION_CREATE)
        self.header_modified = FakeNode(self, text=DIMENSION_MODIFIED)
        # 下拉浮层里的两个选项
        self.option_create = FakeNode(self, text=DIMENSION_CREATE, requires_open=True)
        self.option_modified = FakeNode(
            self, text=DIMENSION_MODIFIED, requires_open=True
        )
        self.dropdown = FakeDropdown(self, self._dropdown_options())

    def _dropdown_options(self) -> list[FakeNode]:
        """浮层里实际有的选项（可模拟「没有更新时间」）。"""
        options = [self.option_create]
        if self.modified_option_present:
            options.append(self.option_modified)
        return options

    def on_click(self, node: FakeNode) -> None:
        if node is self.trigger_node:
            self.dropdown_open = True
            return
        if node in (self.start_input, self.end_input):
            # 真实页面：点开区间输入框会弹出日期选择面板
            self.panel_open = True
            return
        if node is self.option_modified:
            if self.dimension_takes_effect:
                self.dimension = DIMENSION_MODIFIED
                self.trigger_node.text = DIMENSION_MODIFIED
                self.trigger_node.attrs["modelvaluegroup"] = "gmtModified,"
            self.dropdown_open = False
            return
        if node is self.option_create:
            self.dropdown_open = False
            return
        if node is self.confirm_node:
            self.panel_open = False
            self.range_committed = True
            return

    # -- Playwright 表面 ------------------------------------------------
    def locator(self, selector: str) -> FakeLocator:
        if "modelvaluegroup*='gmt'" in selector:
            nodes = [self.trigger_node] if self.dimension_select_present else []
            return FakeLocator(self, nodes)
        if "jx-select-dropdown" in selector or "listbox" in selector:
            return FakeLocator(self, [self.dropdown])
        # ⚠️ 「确定/清空」按钮的选择器里也含 jx-picker-panel → 必须先判它们
        if "is-plain" in selector:
            return FakeLocator(
                self, [self.confirm_node] if self.confirm_present else []
            )
        if "is-text" in selector:
            return FakeLocator(self, [])
        if selector.strip() == ".jx-picker-panel":
            return FakeLocator(self, [self.date_panel])
        if "placeholder*='开始时间'" in selector:
            return FakeLocator(self, [self.start_input] if self.range_inputs else [])
        if "placeholder*='结束时间'" in selector:
            return FakeLocator(self, [self.end_input] if self.range_inputs else [])
        if "jx-range-input" in selector:
            return FakeLocator(self, list(self.range_inputs))
        if selector.startswith("[data-field="):
            return FakeLocator(self, [self.root_node])
        return FakeLocator(self, [])

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        if text in (DIMENSION_CREATE, DIMENSION_MODIFIED):
            nodes: list[FakeNode] = []
            # 真实页面：表格表头排在浮层之前 → 全页搜索第一个命中是表头
            if self.table_header_present:
                if text == DIMENSION_CREATE:
                    nodes.append(self.header_create)
                else:
                    nodes.append(self.header_modified)
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
async def test_clicks_dropdown_option_not_table_header():
    """表格表头里也有「更新时间」这一列 —— 点它只是排序，维度不会变。

    这是 2026-10-26 任务 5526faf9 的真实失败原因：
    全页 get_by_text 的第一个命中是表头，组件点下去 → 维度没切。
    """
    page = FakePage()
    component = _component()

    evidence = await component.apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension == DIMENSION_MODIFIED
    assert page.option_modified.clicks == 1, "必须点下拉浮层里的「更新时间」选项"
    assert page.header_modified.clicks == 0, "不能点表格表头（那是排序列）"


@pytest.mark.asyncio
async def test_reads_dimension_from_trigger_not_table_header():
    """读当前维度必须读触发器，不能把表格表头算进来。"""
    page = FakePage(dimension=DIMENSION_CREATE)
    component = _component()

    assert await component.read_current_dimension(page) == DIMENSION_CREATE

    page.dropdown_open = True
    assert await component.read_current_dimension(page) == DIMENSION_CREATE


@pytest.mark.asyncio
async def test_skips_dimension_switch_when_already_modified():
    """已经是「更新时间」→ 幂等，不该再去点下拉（用户可能已手动选过）。"""
    page = FakePage(dimension=DIMENSION_MODIFIED)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension == DIMENSION_MODIFIED
    assert page.option_modified.clicks == 0


@pytest.mark.asyncio
async def test_fails_when_dimension_select_is_missing():
    """页面上找不到维度 select → 必须明确失败，不能默默采成「创建时间」。"""
    page = FakePage(dimension_select_present=False)

    with pytest.raises(RuntimeError, match="触发器"):
        await _component().apply_incremental_range(page, start=START, end=END)


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
    """「确定」**可用**时要点它（老版页面：点它才算提交区间）。"""
    page = FakePage(confirm_present=True, confirm_enabled_at_once=True)

    await _component().apply_incremental_range(page, start=START, end=END)

    assert page.confirm_node.clicks == 1


@pytest.mark.asyncio
async def test_does_not_click_confirm_while_it_is_still_disabled():
    """真实页面：fill 之后「确定」是 disabled —— 这时候不能去点它。

    disabled 说明 **picker 还没收到值**，是「区间没生效」的信号；
    拿它当成功就是静默失败（增量采集悄悄变成全量采集）。
    """
    page = FakePage(confirm_present=True)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert page.confirm_node.clicks == 0, "「确定」还 disabled 时不能点它"
    assert page.range_committed is True, "得靠 Tab 失焦让 picker 收到值"
    assert evidence.dimension == DIMENSION_MODIFIED


@pytest.mark.asyncio
async def test_closes_panel_with_confirm_after_blur_committed_the_range():
    """Tab 提交了草稿但面板没关 → 此时「确定」变可用 → 再点它把面板收掉。"""
    page = FakePage(confirm_present=True, panel_closes_on_blur=False)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert page.confirm_node.clicks == 1
    assert page.panel_open is False
    assert evidence.dimension == DIMENSION_MODIFIED


@pytest.mark.asyncio
async def test_fails_when_panel_stays_open_after_every_way_to_close_it():
    """面板怎么都收不掉 → 必须明确失败（不能带着开着的面板去点搜索）。"""
    page = FakePage(confirm_present=False, panel_closes_on_blur=False)

    with pytest.raises(RuntimeError, match="日期选择面板"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_reads_sku_total():
    page = FakePage(sku_total_text="SKU总数：11003 库存总价值（元）：223561.83")

    assert await _component().read_sku_total(page) == 11003


@pytest.mark.asyncio
async def test_reads_sku_total_picks_number_right_after_label():
    """同一块区域里别的数字不能被当成 SKU 总数（真实页面上有库存总数/总价值）。"""
    page = FakePage(sku_total_text="仓库清单 0 条记录 SKU总数：1112 库存总数：10971")

    assert await _component().read_sku_total(page) == 1112


@pytest.mark.asyncio
async def test_closes_date_panel_after_filling_range():
    """日期面板开着会挡住「搜索」按钮 → 填完必须把它收起来。"""
    page = FakePage()

    await _component().apply_incremental_range(page, start=START, end=END)

    assert page.panel_open is False, "填完区间后日期面板必须已收起"


@pytest.mark.asyncio
async def test_fails_when_date_panel_cannot_be_closed():
    """面板收不起来 → 必须明确失败（否则采集会卡在点搜索上）。"""
    page = FakePage()

    async def _never_close(page: Any, focus_node: Any = None) -> bool:
        return False

    component = _component()
    component._close_date_panel = _never_close  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="日期选择面板"):
        await component.apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_fails_when_closing_panel_rolled_the_range_back():
    """收面板把区间回滚了 → 必须明确失败。

    这是最危险的一类静默失败：**增量采集悄悄变成全量采集**。
    所以落地证据必须在**收面板之后**读，不能用填充瞬间读到的值。
    """
    page = FakePage(rollback_on_blur=True)

    with pytest.raises(RuntimeError, match="区间未生效"):
        await _component().apply_incremental_range(page, start=START, end=END)


@pytest.mark.asyncio
async def test_range_survives_panel_close_when_picker_accepted_it():
    """picker 收到值（fill + blur）→ 收面板后区间还在 → 证据成立。"""
    page = FakePage(rollback_on_blur=False)

    evidence = await _component().apply_incremental_range(page, start=START, end=END)

    assert evidence.dimension == DIMENSION_MODIFIED
    assert START.split(" ")[0] in evidence.applied_range
    assert END.split(" ")[0] in evidence.applied_range
    assert page.start_input.value == START
    assert page.end_input.value == END


def test_assert_search_results_refreshed_rejects_growth():
    with pytest.raises(RuntimeError, match="反而变多"):
        assert_search_results_refreshed(total_before=100, total_after=200)


def test_assert_search_results_refreshed_rejects_empty():
    with pytest.raises(RuntimeError, match="SKU总数"):
        assert_search_results_refreshed(total_before=100, total_after=0)


def test_assert_search_results_refreshed_accepts_equal_with_warning():
    """筛选前后相等（长窗口覆盖全量）→ 只警告，不报错。"""
    assert_search_results_refreshed(total_before=100, total_after=100)
