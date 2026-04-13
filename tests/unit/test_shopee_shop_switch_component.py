from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.shop_switch import ShopeeShopSwitch


class _FakeLocator:
    def __init__(self, text: str = "", *, visible: bool = True) -> None:
        self._text = text
        self._visible = visible
        self.click = AsyncMock()

    async def count(self) -> int:
        return 1

    async def is_visible(self, *args, **kwargs) -> bool:
        return self._visible

    async def text_content(self) -> str:
        return self._text


class _FakeLocatorGroup:
    def __init__(self, locators: list[_FakeLocator]) -> None:
        self._locators = locators

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int):
        return self._locators[idx]

    @property
    def first(self):
        return self._locators[0] if self._locators else _FakeLocator(visible=False)


class _FakePage:
    def __init__(
        self,
        *,
        selector_map: dict[str, _FakeLocator] | None = None,
        text_map: dict[str, _FakeLocator] | None = None,
    ) -> None:
        self._selector_map = selector_map or {}
        self._text_map = text_map or {}
        self.wait_for_timeout = AsyncMock()

    def locator(self, selector: str):
        locator = self._selector_map.get(selector)
        if locator is None:
            return _FakeLocatorGroup([])
        return _FakeLocatorGroup([locator])

    def get_by_text(self, text: Any, exact: bool = False):
        locator = self._text_map.get(str(text))
        if locator is None:
            return _FakeLocatorGroup([])
        return _FakeLocatorGroup([locator])


@pytest.mark.asyncio
async def test_shopee_shop_switch_noops_when_shop_already_selected() -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={"shop_region": "MY"},
        config={"shop_name": "Demo Shop", "shop_region": "MY"},
    )
    switch = ShopeeShopSwitch(ctx)
    trigger = _FakeLocator("MY Demo Shop")
    page = _FakePage(selector_map={switch.sel.shop_switch_triggers[0]: trigger})

    result = await switch.run(page)

    assert result.success is True
    trigger.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_shop_switch_clicks_region_then_shop() -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={"shop_region": "MY"},
        config={"shop_name": "Demo Shop", "shop_region": "MY"},
    )
    switch = ShopeeShopSwitch(ctx)
    trigger = _FakeLocator("Current Shop")
    region = _FakeLocator("Malaysia")
    shop = _FakeLocator("Demo Shop")
    page = _FakePage(
        selector_map={switch.sel.shop_switch_triggers[0]: trigger},
        text_map={
            "Malaysia": region,
            "Demo Shop": shop,
        },
    )
    switch._wait_shop_selection_applied = AsyncMock(return_value=True)  # type: ignore[method-assign]

    result = await switch.run(page)

    assert result.success is True
    trigger.click.assert_awaited_once()
    region.click.assert_awaited_once()
    shop.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_shopee_shop_switch_noops_when_target_shop_missing() -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    switch = ShopeeShopSwitch(ctx)

    result = await switch.run(_FakePage())

    assert result.success is True
    assert result.message == "no target shop"
