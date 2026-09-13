"""
MiaoshouDatePicker trigger fallback 契约测试
（feat/miaoshou-date-picker-trigger-fallback 配套）

验证 _open() 在不同妙手页面标签下走不同 fallback 路径，并修复后能在采购
页面（"创建日期"）上正常工作。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.platforms.miaoshou.components.date_picker import MiaoshouDatePicker
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


def _clickable_locator():
    """返回一个 mock locator，count()==1, is_visible()==True, click/wait_for 都不抛异常。
    .first 返回自身（Playwright 中 locator.first 是 narrowed locator，行为上等价于 self）。"""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1)
    locator.is_visible = AsyncMock(return_value=True)
    locator.wait_for = AsyncMock(return_value=None)
    locator.click = AsyncMock(return_value=None)
    locator.input_value = AsyncMock(return_value="")
    locator.text_content = AsyncMock(return_value="")
    locator.first = locator
    return locator


def _missing_locator():
    """返回一个"找不到"的 mock locator：click/wait_for 抛异常，count==0。
    用于模拟页面上不存在的元素。"""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=0)
    locator.is_visible = AsyncMock(return_value=False)
    locator.wait_for = AsyncMock(side_effect=Exception("element not found"))
    locator.click = AsyncMock(side_effect=Exception("element not found"))
    locator.input_value = AsyncMock(return_value="")
    locator.text_content = AsyncMock(return_value="")
    locator.first = locator
    return locator


def _make_page(triggers: dict):
    """triggers: {"combobox:开始时间": locator, "combobox:结束时间": locator,
                   "combobox:创建日期": locator, "combobox:创建时间": locator,
                   "text:下单时间": locator, "text:创建日期": locator}

    locator 支持 .click(timeout=...) 与 .wait_for(state="visible", timeout=...) async API。

    未匹配的 role/name 默认行为：
    - button 角色返回 clickable locator（让 _wait_ready 的快捷按钮 / 确定按钮 fallback 不抛错）
    - 其他角色（combobox / textbox 等）返回 missing locator（click 抛异常，让 fallback 链继续）
    """
    page = MagicMock()

    def _resolve(role_or_text, name=None):
        key = f"{role_or_text}:{name}" if name is not None else f"text:{role_or_text}"
        if key in triggers:
            return triggers[key]
        if role_or_text == "button":
            return _clickable_locator()
        return _missing_locator()

    page.get_by_role = MagicMock(side_effect=lambda role, name=None: _resolve(role, name))
    page.get_by_text = MagicMock(side_effect=lambda text, exact=False: _resolve(text))
    page.locator = MagicMock(side_effect=lambda selector: _missing_locator())
    page.wait_for_timeout = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_date_picker_open_prefers_combobox_start_time_when_available():
    """向后兼容：orders 页面"开始时间"combobox 仍走第一优先路径"""
    start_locator = _clickable_locator()
    page = _make_page({"combobox:开始时间": start_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    start_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_create_date_text():
    """采购页面无"开始时间" combobox，但有"创建日期"文本，应走 fallback 打开"""
    create_date_locator = _clickable_locator()
    page = _make_page({"text:创建日期": create_date_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    create_date_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_create_time_text():
    """'创建时间' 也是合法 fallback"""
    create_time_locator = _clickable_locator()
    page = _make_page({"text:创建时间": create_time_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    create_time_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_order_time_text():
    """保留 orders 页面 fallback（"下单时间"）"""
    order_time_locator = _clickable_locator()
    page = _make_page({"text:下单时间": order_time_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    order_time_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_raises_when_no_known_trigger():
    """如果 4 个标签都不在页面上，应抛 RuntimeError 而不是无声失败"""
    page = _make_page({})  # 所有 locator 都不存在（count=0）
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    with pytest.raises(RuntimeError):
        await dp._open(page)


@pytest.mark.asyncio
async def test_date_picker_wait_ready_with_purchase_selectors_looks_for_90_day_not_60_day():
    """_wait_ready() must iterate PurchaseSelectors.date_shortcuts, which include 近90天 (not 近60天).

    Regression test for the bug at purchase_export.py:42 where OrdersSelectors was injected.
    """
    from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
    shortcut_calls: list[str] = []

    def _resolve(role, name=None):
        if role == "button":
            shortcut_calls.append(name or "")
            # _wait_ready() breaks on the first clickable shortcut. To force the
            # loop to iterate through every candidate before matching, make every
            # earlier shortcut raise and only the last one (近90天) succeed.
            if name == "近90天":
                return _clickable_locator()
            return _missing_locator()
        return _missing_locator()

    page = MagicMock()
    page.get_by_role = MagicMock(side_effect=_resolve)
    page.wait_for_timeout = AsyncMock()
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=PurchaseSelectors())
    await dp._wait_ready(page)
    # Purchase shortcuts are 今天/昨天/近7天/近30天/近90天 — the loop must attempt 近90天, not 近60天.
    assert "近90天" in shortcut_calls
    assert "近60天" not in shortcut_calls


@pytest.mark.asyncio
async def test_date_picker_wait_ready_does_not_raise_when_confirm_button_missing():
    """_wait_ready() must NOT raise if the date panel has no '确定' button.

    Some miaoshou panels apply the selected range automatically when the
    custom textboxes are filled, without an explicit confirm button.
    """
    page = MagicMock()

    def _resolve(role, name=None):
        if role == "button":
            # Shortcuts return a clickable locator; the confirm button returns missing.
            if name in ("今天", "昨天", "近7天", "近30天", "近90天"):
                return _clickable_locator()
            return _missing_locator()
        return _missing_locator()

    page.get_by_role = MagicMock(side_effect=_resolve)
    page.wait_for_timeout = AsyncMock()
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    # Must not raise even though the "确定" button is missing.
    await dp._wait_ready(page)
