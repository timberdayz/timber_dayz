from __future__ import annotations

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.filters import MiaoshouFilters


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


class _FakeLocator:
    def __init__(
        self,
        *,
        checked: bool = False,
        evaluate_checked: bool | None = None,
        raise_on_visible_wait: bool = False,
    ) -> None:
        self.checked = checked
        self.evaluate_checked = evaluate_checked
        self.raise_on_visible_wait = raise_on_visible_wait
        self.clicked = 0
        self.wait_calls: list[tuple[str, int | None]] = []

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def wait_for(self, state: str = "visible", timeout: int | None = None) -> None:
        if state == "visible" and self.raise_on_visible_wait:
            raise TimeoutError("locator remained hidden")
        self.wait_calls.append((state, timeout))

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1

    async def is_checked(self) -> bool:
        return self.checked

    async def evaluate(self, script: str) -> bool:
        if self.evaluate_checked is None:
            raise RuntimeError("evaluate not configured")
        return self.evaluate_checked


class _FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakeTooltip:
    def __init__(
        self,
        *,
        option: _FakeLocator,
        full_select_checkbox: _FakeLocator,
        full_select_label: _FakeLocator,
    ) -> None:
        self.option = option
        self.full_select_checkbox = full_select_checkbox
        self.full_select_label = full_select_label
        self.wait_calls: list[tuple[str, int | None]] = []

    @property
    def first(self) -> "_FakeTooltip":
        return self

    async def wait_for(self, state: str = "visible", timeout: int | None = None) -> None:
        self.wait_calls.append((state, timeout))

    def get_by_role(self, role: str, name=None):  # noqa: ANN001
        if role == "checkbox" and name == "全选":
            return self.full_select_checkbox
        if role == "option":
            return self.option
        raise AssertionError(f"unexpected tooltip.get_by_role({role!r}, {name!r})")

    def get_by_text(self, text: str, exact: bool = False):  # noqa: ANN001
        if text == "全选":
            return self.full_select_label
        raise AssertionError(f"unexpected tooltip.get_by_text({text!r})")


class _FakePage:
    def __init__(
        self,
        *,
        trigger: _FakeLocator,
        full_select: _FakeLocator,
        tooltip: _FakeTooltip | None = None,
    ) -> None:
        self.trigger = trigger
        self.full_select = full_select
        self.tooltip = tooltip
        self.keyboard = _FakeKeyboard()

    def get_by_role(self, role: str, name=None):  # noqa: ANN001
        if role == "combobox":
            return self.trigger
        if role == "checkbox" and name == "全选":
            return self.full_select
        if role == "tooltip" and self.tooltip is not None:
            return self.tooltip
        raise AssertionError(f"unexpected get_by_role({role!r}, {name!r})")


@pytest.mark.asyncio
async def test_miaoshou_filters_does_not_click_full_select_when_overlay_checkbox_is_already_selected() -> None:
    component = MiaoshouFilters(_ctx())
    trigger = _FakeLocator()
    full_select = _FakeLocator(
        checked=False,
        evaluate_checked=True,
    )
    page = _FakePage(trigger=trigger, full_select=full_select)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert trigger.clicked == 1
    assert full_select.clicked == 0
    assert page.keyboard.pressed == ["Escape"]


@pytest.mark.asyncio
async def test_miaoshou_filters_clicks_full_select_when_overlay_checkbox_is_not_selected() -> None:
    component = MiaoshouFilters(_ctx())
    trigger = _FakeLocator()
    full_select = _FakeLocator(
        checked=False,
        evaluate_checked=False,
    )
    page = _FakePage(trigger=trigger, full_select=full_select)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert trigger.clicked == 1
    assert full_select.clicked == 1
    assert page.keyboard.pressed == ["Escape"]


@pytest.mark.asyncio
async def test_miaoshou_filters_uses_visible_overlay_instead_of_waiting_on_hidden_checkbox_input() -> None:
    component = MiaoshouFilters(_ctx())
    trigger = _FakeLocator()
    hidden_checkbox = _FakeLocator(
        checked=False,
        evaluate_checked=False,
        raise_on_visible_wait=True,
    )
    full_select_label = _FakeLocator()
    tooltip = _FakeTooltip(
        option=_FakeLocator(),
        full_select_checkbox=hidden_checkbox,
        full_select_label=full_select_label,
    )
    page = _FakePage(trigger=trigger, full_select=hidden_checkbox, tooltip=tooltip)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert trigger.clicked == 1
    assert full_select_label.clicked == 1
    assert page.keyboard.pressed == ["Escape"]
