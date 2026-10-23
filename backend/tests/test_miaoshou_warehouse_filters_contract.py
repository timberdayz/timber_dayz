"""妙手仓库范围筛选组件的 contract 与行为测试。

行为用例复现线上 task 637 / `7bb2a92e-a0eb-4129-ba5c-6237b852c909` 的失败路径：
点击仓库范围下拉框时，`jx-select__selected-item jx-select__placeholder is-transparent`
拦截命中测试 → `Locator.click: Timeout 1500ms exceeded`。
"""

from __future__ import annotations

import pytest

from miaoshou_page_fakes import FakeLocator, FakePage, FakeTagList
from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.warehouse_filters import (
    MiaoshouWarehouseFilters,
)

CONTAINER_XPATH = "xpath=ancestor::*[contains(@class,'jx-select')][1]"


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def _overlay(*, checked: bool = False) -> FakeLocator:
    """模拟已打开的下拉浮层，内含「全选」复选框与文字。"""
    full_select = FakeLocator(checked=checked, evaluate_checked=checked)
    return FakeLocator(
        children={
            "role:checkbox:全选": full_select,
            "text:全选": FakeLocator(),
        }
    )


def _container(selected_tags: list[str] | None) -> FakeLocator:
    """构造 .jx-select 容器外壳，含选中区与 .jx-tag 集合。"""
    return FakeLocator(
        children={
            ".jx-select__selected-item": FakeLocator(
                children={".jx-tag": FakeTagList(selected_tags or [])},
                count=1 if selected_tags else 0,
            )
        }
    )


def _page(
    *,
    trigger_intercepted: bool = False,
    trigger_always_fails: bool = False,
    label_available: bool = True,
    container_available: bool = True,
    overlay: FakeLocator | None = None,
    selected_tags: list[str] | None = None,
) -> FakePage:
    """构造妙手仓库清单页的假 page。

    ⚠️ **遮挡必须挂在 label_input 上**：`_warehouse_scope_trigger` 的
    **第一个**候选是 `page.get_by_label(re.compile("仓库"))`，假对象里它恒可见 →
    直接返回。**真实页面上被遮挡的正是这个 input**（`.jx-select__input` 被
    `.jx-select__selected-item` 盖住），所以形态 A 的拦截要挂在这里。

    `trigger_intercepted`：普通 click 被覆盖层拦截，但 `force=True` 能穿透
    （对应真实 Playwright 的 actionability 检查语义）。
    `trigger_always_fails`：任何点击都失败（连 force 也失败）——用于逼出层 D。
    """
    label_input = FakeLocator(
        visible=label_available,
        count=1 if label_available else 0,
        intercept_clicks=trigger_intercepted,
        fail_clicks=99 if trigger_always_fails else 0,
    )
    container = _container(selected_tags)
    if container_available:
        label_input.children = {CONTAINER_XPATH: container}

    combobox_trigger = FakeLocator(
        intercept_clicks=trigger_intercepted,
        fail_clicks=99 if trigger_always_fails else 0,
    )

    return FakePage(
        locators={
            "label:仓库": label_input,
            "role:combobox:None": combobox_trigger,
            "role:tooltip:None": (
                overlay if overlay is not None else FakeLocator(count=0)
            ),
        }
    )


def _container_of(page: FakePage) -> FakeLocator:
    return page.locators["label:仓库"].children[CONTAINER_XPATH]


def test_miaoshou_warehouse_filters_component_declares_miaoshou_platform():
    assert MiaoshouWarehouseFilters.platform == "miaoshou"
    assert MiaoshouWarehouseFilters.component_type == "filters"
    assert MiaoshouWarehouseFilters.data_domain is None


def test_miaoshou_warehouse_filters_constructor_accepts_inventory_selectors():
    selectors = InventorySelectors()
    component = MiaoshouWarehouseFilters(_ctx(), selectors)

    assert component.sel is selectors


@pytest.mark.asyncio
async def test_warehouse_filters_opens_dropdown_by_clicking_container_when_trigger_is_covered() -> (
    None
):
    """层 A 治本：触发器被 placeholder 遮挡时，改点 .jx-select 容器外壳即可打开下拉。

    这是线上 task 637 的复现用例——原实现点的是被遮挡的 input。
    """
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=True, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    # 层 A 生效：容器被点开
    assert _container_of(page).clicked == 1
    # 组件不再依赖点那个被遮挡的触发器
    assert page.locators["label:仓库"].click_calls == []
    assert overlay.get_by_role("checkbox", name="全选").clicked == 0


@pytest.mark.asyncio
async def test_warehouse_filters_penetrates_cover_with_force_click_when_container_unavailable() -> (
    None
):
    """层 B：容器定位不到时，用 force=True 穿透遮挡点触发器。"""
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=True, container_available=False, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    trigger = page.locators["label:仓库"]
    assert trigger.click_calls == [(3000, True)]  # force=True 已传入，且穿透成功


@pytest.mark.asyncio
async def test_warehouse_filters_skips_dropdown_when_scope_already_all_selected() -> (
    None
):
    """形态 B：已全选（折叠出 "+ N" 标签）时不开下拉直接返回。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(selected_tags=["仓库A", "+ 4"])

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is True


@pytest.mark.asyncio
async def test_warehouse_filters_does_not_mistake_other_select_for_all_selected() -> (
    None
):
    """层 C 不得误判：页面上**别的** jx-select 处于 "+ N" 折叠态时，
    不能因此跳过仓库范围筛选（否则导出数据范围错误）。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(overlay=_overlay(checked=True))
    # 页面级存在另一个处于 "+ N" 折叠态的 jx-select（店铺 / 分类等）
    page.locators[".jx-select"] = FakeLocator(
        children={
            ".jx-select__selected-item": FakeLocator(
                children={".jx-tag": FakeTagList(["店铺A", "+ 9"])},
                count=1,
            )
        }
    )

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is not True


@pytest.mark.asyncio
async def test_warehouse_filters_tries_keyboard_fallback_then_reports_stage_name() -> (
    None
):
    """A/B/C 全失败后触发层 D 键盘兜底，并给出带阶段名的失败信息。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(
        trigger_always_fails=True,
        label_available=False,
        container_available=False,
        overlay=FakeLocator(count=0),
    )

    result = await component.run(page, {"select_all": True})

    assert result.success is False
    assert page.keyboard.pressed == ["Enter"]
    assert "warehouse_scope_open_failed" in (result.message or "")
