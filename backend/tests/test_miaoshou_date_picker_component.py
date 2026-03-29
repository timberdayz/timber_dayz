from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.platforms.miaoshou.components.date_picker import MiaoshouDatePicker


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


class _FakeLocator:
    def __init__(self) -> None:
        self.clicked = 0
        self.wait_calls: list[tuple[str, int | None]] = []

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1

    async def wait_for(self, state: str = "visible", timeout: int | None = None) -> None:
        self.wait_calls.append((state, timeout))


class _UnexpectedLocator(_FakeLocator):
    async def click(self, timeout: int | None = None) -> None:
        raise AssertionError("unexpected click")


class _FakePage:
    def __init__(self) -> None:
        self.start_time = _FakeLocator()
        self.end_time = _FakeLocator()
        self.text_trigger = _UnexpectedLocator()

    def get_by_role(self, role: str, name=None):  # noqa: ANN001
        if role == "combobox" and name == "开始时间":
            return self.start_time
        if role == "combobox" and name == "结束时间":
            return self.end_time
        raise AssertionError(f"unexpected get_by_role({role!r}, {name!r})")

    def get_by_text(self, text: str, exact: bool = False):  # noqa: ANN001
        if "下单时间" in text:
            return self.text_trigger
        raise AssertionError(f"unexpected get_by_text({text!r})")


@pytest.mark.asyncio
async def test_miaoshou_date_picker_open_prefers_named_time_combobox_trigger() -> None:
    component = MiaoshouDatePicker(_ctx())
    page = _FakePage()
    component._wait_ready = AsyncMock()  # type: ignore[method-assign]

    await component._open(page)

    assert page.start_time.clicked == 1
    assert page.end_time.clicked == 0


@pytest.mark.asyncio
async def test_miaoshou_date_picker_preset_path_does_not_click_confirm_button() -> None:
    component = MiaoshouDatePicker(_ctx())
    page = _FakePage()
    preset_button = _FakeLocator()
    confirm_button = _UnexpectedLocator()

    async def _fake_open(current_page) -> None:
        return None

    component._open = _fake_open  # type: ignore[method-assign]

    def _get_by_role(role: str, name=None):  # noqa: ANN001
        if role == "button" and name == "昨天":
            return preset_button
        if role == "button" and name == "确定":
            return confirm_button
        raise AssertionError(f"unexpected get_by_role({role!r}, {name!r})")

    page.get_by_role = _get_by_role  # type: ignore[method-assign]

    result = await component.run(page, option=DateOption.YESTERDAY)

    assert result.success is True
    assert preset_button.clicked == 1
