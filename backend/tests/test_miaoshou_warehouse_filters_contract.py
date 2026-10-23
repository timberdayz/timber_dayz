"""妙手仓库范围筛选组件的行为测试（对齐 2026-10-23 真实页面取证）。

真实页面结构（取证结论见 `inventory_config.py` 注释）::

    div.jx-col.jx-col-6[data-field="warehouseIds"]        ← 稳定锚点
      └── div.jx-form-item
            └── div.jx-select.jx-select--small.pro-select  ← 层 C 根节点
                  [modelvaluegroup="684506,563787,563786,381635,299699"]
                  ├── div.jx-select__wrapper                ← 层 A 点击目标
                  │     └── input.jx-select__input[role=combobox]
                  └── div.jx-select__selected-item
                        └── span.jx-tag × 2（"菲律宾3店-时尚箱包" / "+ 4"）

    div.jx-popper[role=tooltip]
      └── div.jx-select-dropdown.is-multiple.pro-select-popper   ← 浮层根
            ├── div.jx-select-dropdown__header
            │     └── label.jx-checkbox[.is-checked]        ← 「全选」可点击目标
            │           ├── input.jx-checkbox__original     ← 视觉隐藏，点不到
            │           └── span.jx-checkbox__label「全选」
            └── div.jx-scrollbar
                  └── ul.jx-select-dropdown__list[role=listbox]

两个关键业务事实（决定本文件的断言口径）：

1. **仓库筛选是可选筛选项，「不选 = 全选」**（空态与全选态的 SKU 总数、
   分页、表格内容完全一致）→ 显式勾选全选失败只能**降级**（记告警），
   不能让整个导出任务失败。
2. **「全选」的可点击目标是 `label.jx-checkbox`**：真实 input
   `input.jx-checkbox__original` 能定位（count=1）但视觉隐藏、点不到；
   点击 label 后 header checkbox 的 class 去掉 `is-checked`，
   `modelvaluegroup` 变空串、`.jx-tag` 清空（再点一次完全恢复）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest

from miaoshou_page_fakes import FakeLocator, FakePage
from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.warehouse_filters import (
    MiaoshouWarehouseFilters,
)

# 全选态实测值（`modelvaluegroup` 属性 + `.jx-tag` 文本）
ALL_SELECTED_VALUES = "684506,563787,563786,381635,299699"
ALL_SELECTED_TAGS = ["菲律宾3店-时尚箱包", "+ 4"]


def _parse_field_selector(selector: str) -> tuple[str, str]:
    """从 `[data-field='warehouseIds']` 解析出 (属性名, 属性值)。"""
    match = re.search(r"\[([A-Za-z_][\w-]*)=['\"]([^'\"]+)['\"]\]", selector)
    if match is None:
        raise AssertionError(f"仓库范围字段选择器缺少属性断言: {selector!r}")
    return match.group(1), match.group(2)


_FIELD_ATTR, _FIELD_VALUE = _parse_field_selector(
    InventorySelectors().warehouse_scope_field_selector
)


def _node(selector: str, **kwargs: Any) -> FakeLocator:
    """建节点的简写。"""
    return FakeLocator(selector=selector, **kwargs)


@dataclass
class _WarehouseDom:
    """夹具里可被断言的节点。"""

    page: FakePage
    field_box: FakeLocator
    select_root: FakeLocator
    selected_item: FakeLocator
    wrapper: FakeLocator
    trigger: FakeLocator
    overlay: FakeLocator
    popper: FakeLocator
    listbox: FakeLocator
    full_select_label: FakeLocator | None
    full_select_input: FakeLocator
    other_select: FakeLocator | None


class _StepRecorder:
    """记录 report_step 事件（用于断言动作文本）。

    必须是**同步**回调：`call_step_callback` 用
    `asyncio.iscoroutinefunction(ctx.step_callback)` 判断，而实例上的
    异步 `__call__` 不会被识别成协程函数。
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((event_type, data))

    def actions(self, event_type: str = "step_success") -> list[str]:
        return [
            str(data.get("action", ""))
            for kind, data in self.events
            if kind == event_type
        ]


def _ctx(recorder: _StepRecorder | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
        step_callback=recorder,
    )


def _build_field(
    *,
    model_value: str | None,
    trigger_intercepted: bool,
    trigger_click_fails: bool,
    wrapper_click_fails: bool,
    open_dropdown: Any,
) -> dict[str, FakeLocator]:
    """构造仓库筛选字段：锚点容器 → select 根 → wrapper/input + 选中区。"""
    trigger = _node(
        "input.jx-select__input.is-small",
        attributes={
            "role": "combobox",
            "aria-haspopup": "listbox",
            "aria-expanded": "false",
            "aria-controls": "jx-id-8191-471",
        },
        label_text="仓库",
        intercept_clicks=trigger_intercepted,
        fail_clicks=99 if trigger_click_fails else 0,
        on_click=open_dropdown,
    )
    wrapper = _node(
        "div.jx-select__wrapper",
        fail_clicks=99 if wrapper_click_fails else 0,
        on_click=open_dropdown,
    )
    wrapper.add_child(trigger)
    selected_item = _node("div.jx-select__selected-item")
    select_root = _node(
        "div.jx-select.jx-select--small.pro-select",
        attributes={} if model_value is None else {"modelvaluegroup": model_value},
    )
    select_root.add_child(wrapper)
    select_root.add_child(selected_item)
    form_item = _node("div.jx-form-item.jx-form-item--small")
    form_item.add_child(_node("div.jx-form-item__label", text="仓库"))
    form_item.add_child(select_root)
    field_box = _node("div.jx-col.jx-col-6", attributes={_FIELD_ATTR: _FIELD_VALUE})
    field_box.add_child(form_item)
    return {
        "field_box": field_box,
        "select_root": select_root,
        "selected_item": selected_item,
        "wrapper": wrapper,
        "trigger": trigger,
    }


def _build_listbox() -> FakeLocator:
    """构造浮层里的仓库列表（`ul[role=listbox]`，5 行仓库选项）。"""
    listbox = _node("ul.jx-select-dropdown__list", attributes={"role": "listbox"})
    for _ in range(5):
        row = _node("li.jx-select-dropdown__item")
        row.add_child(_node("label.jx-checkbox.jx-checkbox--small.pro-checkbox"))
        listbox.add_child(row)
    return listbox


def _build_overlay(
    *, checked: bool, label_present: bool, click_fails: bool
) -> dict[str, Any]:
    """构造下拉浮层与头部「全选」复选框（label 可点击 / input 隐藏点不到）。"""
    label: FakeLocator | None = None
    hidden_input = _node(
        "input.jx-checkbox__original",
        attributes={"type": "checkbox"},
        checked=checked,
        fail_clicks=99,  # 视觉隐藏：能定位（count=1）但点不到
    )
    if label_present:
        label = _node(
            "label.jx-checkbox.jx-checkbox--small"
            + (".is-checked" if checked else "")
            + ".pro-checkbox",
            fail_clicks=99 if click_fails else 0,
        )
        label.add_child(hidden_input)
        label.add_child(_node("span.jx-checkbox__label", text="全选"))
    header = _node("div.jx-select-dropdown__header")
    if label is not None:
        header.add_child(label)
    else:
        header.add_child(hidden_input)
    scrollbar = _node("div.jx-scrollbar")
    scrollbar.add_child(_build_listbox())
    overlay = _node(
        "div.jx-select-dropdown.is-multiple.pro-select-popper", visible=False
    )
    overlay.add_child(header)
    overlay.add_child(scrollbar)
    popper = _node(
        "div.jx-popper.is-pure.is-light.jx-tooltip.jx-select__popper",
        attributes={"role": "tooltip"},
        visible=False,
    )
    popper.add_child(overlay)
    return {
        "overlay": overlay,
        "popper": popper,
        "header": header,
        "listbox": scrollbar.child_nodes[0],
        "label": label,
        "hidden_input": hidden_input,
    }


def _replace_tags(selected_item: FakeLocator, texts: list[str]) -> None:
    """把选中区的 `.jx-tag` 换成给定文本。"""
    selected_item.child_nodes = []
    for text in texts:
        selected_item.add_child(_node("span.jx-tag", text=text))


def _make_toggle(
    *,
    label: FakeLocator,
    hidden_input: FakeLocator,
    select_root: FakeLocator,
    selected_item: FakeLocator,
) -> Any:
    """构造「点『全选』在空态 / 全选态之间切换」的副作用。

    实测：点击 label 后 header checkbox 的 class 去掉 `is-checked`，
    `modelvaluegroup` 变空串、`.jx-tag` 清空；再点一次完全恢复。
    """

    def _toggle() -> None:
        if "is-checked" in label.class_names:
            label.class_names.discard("is-checked")
            select_root.set_attribute("modelvaluegroup", "")
            hidden_input.checked = False
            _replace_tags(selected_item, [])
            return
        label.class_names.add("is-checked")
        select_root.set_attribute("modelvaluegroup", ALL_SELECTED_VALUES)
        hidden_input.checked = True
        _replace_tags(selected_item, list(ALL_SELECTED_TAGS))

    return _toggle


def _build_other_select(tags: list[str]) -> FakeLocator:
    """构造页面上**另一个** jx-select（商品 SKU / 模糊匹配等筛选）。"""
    other = _node(
        "div.jx-select.jx-select--small.pro-select",
        attributes={"modelvaluegroup": ""},
    )
    selected = _node("div.jx-select__selected-item")
    for text in tags:
        selected.add_child(_node("span.jx-tag", text=text))
    other.add_child(selected)
    return other


def _build_root(
    *,
    field: dict[str, FakeLocator],
    anchor_available: bool,
    other_select: FakeLocator | None,
    popper: FakeLocator,
) -> FakeLocator:
    """组装页面根节点。

    `anchor_available=False` 时不挂字段容器：触发器直接挂在根下，
    `[data-field=...]` 锚点与 xpath 祖先链同时失效（逼出层 B 兜底）。

    ⚠️ 另一个 jx-select 排在**仓库字段之前**：历史上「裸 `.jx-select` 全页
    扫描」正是先命中了它，才把「+ 9」误当成「仓库已全选」。
    """
    root = _node("body")
    if other_select is not None:
        root.add_child(other_select)
    if anchor_available:
        root.add_child(field["field_box"])
    else:
        root.add_child(field["trigger"])
    root.add_child(popper)
    return root


def _wire_toggle(
    *, overlay_parts: dict[str, Any], field: dict[str, FakeLocator], enabled: bool
) -> None:
    """把「点『全选』在空态 / 全选态之间切换」的副作用接到 label 上。"""
    label = overlay_parts["label"]
    if label is None or not enabled:
        return
    label.on_click = _make_toggle(
        label=label,
        hidden_input=overlay_parts["hidden_input"],
        select_root=field["select_root"],
        selected_item=field["selected_item"],
    )


def _build_parts(
    *,
    model_value: str | None,
    tags: list[str] | None,
    label_present: bool,
    full_select_click_fails: bool,
    full_select_stays_unchecked: bool,
    wrapper_click_fails: bool,
    trigger_click_fails: bool,
    trigger_intercepted: bool,
) -> tuple[dict[str, FakeLocator], dict[str, Any]]:
    """构造浮层与仓库字段（并接好下拉打开、勾选切换的副作用）。

    - `model_value`：`modelvaluegroup` 属性值；`None` 表示属性不存在。
    - `tags`：`.jx-tag` 文本；`None` 表示由 `model_value` 推导。
    - `label_present`：浮层头部是否存在可点击的 `label.jx-checkbox`。
    - `full_select_click_fails`：点「全选」抛错（模拟点不到）。
    - `full_select_stays_unchecked`：点「全选」成功但状态不变（回读未选中）。
    """
    checked = model_value == ALL_SELECTED_VALUES
    effective_tags = list(ALL_SELECTED_TAGS) if checked else []
    if tags is not None:
        effective_tags = list(tags)

    overlay_parts = _build_overlay(
        checked=checked,
        label_present=label_present,
        click_fails=full_select_click_fails,
    )
    overlay = overlay_parts["overlay"]
    popper = overlay_parts["popper"]

    def _open_dropdown() -> None:
        overlay.visible = True
        popper.visible = True

    field = _build_field(
        model_value=model_value,
        trigger_intercepted=trigger_intercepted,
        trigger_click_fails=trigger_click_fails,
        wrapper_click_fails=wrapper_click_fails,
        open_dropdown=_open_dropdown,
    )
    _replace_tags(field["selected_item"], effective_tags)
    _wire_toggle(
        overlay_parts=overlay_parts,
        field=field,
        enabled=not full_select_stays_unchecked,
    )
    return field, overlay_parts


def _build_dom(
    *,
    model_value: str | None = "",
    tags: list[str] | None = None,
    label_present: bool = True,
    full_select_click_fails: bool = False,
    full_select_stays_unchecked: bool = False,
    wrapper_click_fails: bool = False,
    trigger_click_fails: bool = False,
    trigger_intercepted: bool = False,
    anchor_available: bool = True,
    other_select_tags: list[str] | None = None,
) -> _WarehouseDom:
    """构造妙手仓库清单页的假 DOM（参数含义见 `_build_parts`）。"""
    field, overlay_parts = _build_parts(
        model_value=model_value,
        tags=tags,
        label_present=label_present,
        full_select_click_fails=full_select_click_fails,
        full_select_stays_unchecked=full_select_stays_unchecked,
        wrapper_click_fails=wrapper_click_fails,
        trigger_click_fails=trigger_click_fails,
        trigger_intercepted=trigger_intercepted,
    )
    other_select = _build_other_select(other_select_tags) if other_select_tags else None
    root = _build_root(
        field=field,
        anchor_available=anchor_available,
        other_select=other_select,
        popper=overlay_parts["popper"],
    )
    return _WarehouseDom(
        page=FakePage(root=root),
        field_box=field["field_box"],
        select_root=field["select_root"],
        selected_item=field["selected_item"],
        wrapper=field["wrapper"],
        trigger=field["trigger"],
        overlay=overlay_parts["overlay"],
        popper=overlay_parts["popper"],
        listbox=overlay_parts["listbox"],
        full_select_label=overlay_parts["label"],
        full_select_input=overlay_parts["hidden_input"],
        other_select=other_select,
    )


# ── 组件契约 ──────────────────────────────────────────────────────────


def test_miaoshou_warehouse_filters_component_declares_miaoshou_platform() -> None:
    assert MiaoshouWarehouseFilters.platform == "miaoshou"
    assert MiaoshouWarehouseFilters.component_type == "filters"
    assert MiaoshouWarehouseFilters.data_domain is None


def test_miaoshou_warehouse_filters_constructor_accepts_inventory_selectors() -> None:
    selectors = InventorySelectors()

    component = MiaoshouWarehouseFilters(_ctx(), selectors)

    assert component.sel is selectors


# ── 用例 1：层 A 用 data-field 锚点定位 ───────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_opens_dropdown_by_clicking_data_field_anchor() -> None:
    """层 A：用 `[data-field='warehouseIds']` 锚点找容器并点开下拉。

    触发器 input（被 placeholder 盖住）**不能**被点；点的是锚点下的
    `.jx-select__wrapper`，随后下拉真的弹出了。
    """
    dom = _build_dom()
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert dom.trigger.clicked == 0
    assert dom.trigger.click_calls == []
    assert dom.wrapper.clicked == 1
    assert dom.overlay.visible is True


# ── 用例 2：浮层根取 .jx-select-dropdown，「全选」点 label ────────────


@pytest.mark.asyncio
async def test_warehouse_filters_clicks_full_select_label_inside_dropdown_root() -> (
    None
):
    """浮层根必须是 `.jx-select-dropdown`（含 header），「全选」点 label。

    内层 listbox 里没有 header 的复选框；真实 input 隐藏点不到，
    可点击目标是 `label.jx-checkbox`。
    """
    dom = _build_dom()
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert dom.full_select_label is not None
    assert dom.full_select_label.clicked == 1
    # 隐藏 input 不能被点（能定位但点不到）
    assert dom.full_select_input.clicked == 0
    # listbox 里没有 header 的复选框 → 浮层根不能是 listbox
    assert await dom.listbox.locator(".jx-checkbox__original").count() == 0
    # 实测：复选框不是 role="checkbox"，按角色查找命中 0 个
    assert await dom.page.get_by_role("checkbox", name="全选").count() == 0


# ── 用例 3 / 4：层 C 前置检测（modelvaluegroup）──────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_skips_dropdown_when_model_value_attribute_full() -> (
    None
):
    """层 C：`modelvaluegroup` 非空 → 判定为已全选，不开下拉。"""
    dom = _build_dom(model_value=ALL_SELECTED_VALUES)
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is True
    assert dom.wrapper.clicked == 0
    assert dom.full_select_label is not None
    assert dom.full_select_label.clicked == 0


@pytest.mark.asyncio
async def test_warehouse_filters_proceeds_when_model_value_attribute_empty() -> None:
    """层 C：`modelvaluegroup` 为空串 → 不判为已全选，继续走 action。"""
    dom = _build_dom(model_value="")
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is not True
    assert dom.wrapper.clicked == 1
    assert dom.full_select_label is not None
    assert dom.full_select_label.clicked == 1


# ── 用例 5：tag 兜底判据 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_detects_all_selected_by_tag_fallback() -> None:
    """层 C 兜底：读不到 `modelvaluegroup` 时，用 `.jx-tag`（含 "+ 4"）判定。"""
    dom = _build_dom(model_value=None, tags=list(ALL_SELECTED_TAGS))
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is True
    assert dom.wrapper.clicked == 0


@pytest.mark.asyncio
async def test_warehouse_filters_does_not_detect_all_selected_with_single_tag() -> None:
    """层 C 兜底：只有 1 个 `.jx-tag` 表示只选了一项，**不能**判为全选。"""
    dom = _build_dom(model_value=None, tags=["菲律宾3店-时尚箱包"])
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is not True
    assert dom.wrapper.clicked == 1


# ── 用例 6 / 7 / 8：显式全选成功与降级 ────────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_degrades_without_fatal_when_full_select_fails() -> (
    None
):
    """「显式勾选全选」失败 → **降级不致命**（不选 = 全选）。

    仓库筛选是可选筛选项，显式全选失败只能记告警，不能拖垮整个导出任务。
    """
    dom = _build_dom(full_select_click_fails=True)
    recorder = _StepRecorder()
    component = MiaoshouWarehouseFilters(_ctx(recorder))

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("scope_all_selected") is False
    assert result.details.get("scope_degraded_reason")
    assert any("已按默认范围（全部仓库）继续" in a for a in recorder.actions())


@pytest.mark.asyncio
async def test_warehouse_filters_degrades_without_fatal_when_post_check_unconfirmed() -> (
    None
):
    """post-check 回读仍未选中 → 同样降级不致命，不再抛 verify_failed。"""
    dom = _build_dom(full_select_stays_unchecked=True)
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("scope_all_selected") is False
    assert "warehouse_scope_verify_failed" in str(
        result.details.get("scope_degraded_reason")
    )
    assert dom.full_select_label is not None
    assert dom.full_select_label.clicked == 1


@pytest.mark.asyncio
async def test_warehouse_filters_reports_all_selected_on_successful_check() -> None:
    """正常路径：勾选成功 → `scope_all_selected` 为真且没有降级字段。"""
    dom = _build_dom()
    recorder = _StepRecorder()
    component = MiaoshouWarehouseFilters(_ctx(recorder))

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("scope_all_selected") is True
    assert "scope_degraded_reason" not in result.details
    assert "scope_degraded_note" not in result.details
    assert any("已全选" in a for a in recorder.actions())


# ── 用例 9：层 D 键盘兜底 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_tries_keyboard_fallback_then_degrades() -> None:
    """层 A / 层 B 全失败 → 试层 D 键盘；键盘也失败 → 降级不致命。"""
    dom = _build_dom(
        anchor_available=False,
        wrapper_click_fails=True,
        trigger_click_fails=True,
    )
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert "Enter" in dom.page.keyboard.pressed
    assert result.details.get("scope_all_selected") is False
    assert result.details.get("scope_degraded_reason")


# ── 用例 10：不得误判别的 select ──────────────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_does_not_mistake_other_select_for_all_selected() -> (
    None
):
    """页面上另一个 jx-select 处于 "+ 9" 折叠态时，不得判为「仓库已全选」。

    裸 `.jx-select` 全页扫描会把「商品 SKU」等筛选误判成仓库已全选 →
    直接跳过开下拉 → 导出数据范围错误。
    """
    dom = _build_dom(model_value="", other_select_tags=["商品A", "+ 9"])
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is not True
    assert dom.wrapper.clicked == 1


# ── 兜底路径：层 B force 点击 / 隐藏 input 点不到 ─────────────────────


@pytest.mark.asyncio
async def test_warehouse_filters_layer_b_force_click_penetrates_covered_trigger() -> (
    None
):
    """层 B：锚点不可用时，用 force=True 穿透遮挡点触发器（线上 task 637 复现）。"""
    dom = _build_dom(anchor_available=False, trigger_intercepted=True)
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    # force=True 已传入，且穿透成功
    assert dom.trigger.click_calls == [(3000, True)]
    assert dom.overlay.visible is True


@pytest.mark.asyncio
async def test_warehouse_filters_degrades_when_only_hidden_input_is_clickable() -> None:
    """没有可点击的 label 时兜底到隐藏 input → 点不到 → 降级不致命。"""
    dom = _build_dom(label_present=False)
    component = MiaoshouWarehouseFilters(_ctx())

    result = await component.run(dom.page, {"select_all": True})

    assert result.success is True
    assert result.details.get("scope_all_selected") is False
    assert dom.full_select_input.clicked == 0
