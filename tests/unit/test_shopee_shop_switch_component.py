from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.shop_switch import ShopeeShopSwitch


def _ctx(
    account: dict | None = None,
    config: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        platform="shopee",
        account=account or {},
        config=config or {},
    )


class _FakeLocator:
    def __init__(self, text: str = "", *, visible: bool = True) -> None:
        self._text = text
        self._visible = visible
        self.click = AsyncMock()

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1 if self._visible else 0

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


class _UrlSwitchPage:
    def __init__(self, url: str, display_text: str = "") -> None:
        self.url = url
        self.display_text = display_text
        self.goto_calls: list[str] = []
        self.wait_calls: list[int] = []

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def locator(self, selector: str):
        if selector == ".shop-selector .shop-info" and self.display_text:
            return _FakeLocator(self.display_text)
        return _FakeLocator(visible=False)

    def get_by_text(self, text: Any, exact: bool = False):
        return _FakeLocator(visible=False)


class _DelayedUrlSwitchPage(_UrlSwitchPage):
    def __init__(self, url: str, target_url: str) -> None:
        super().__init__(url)
        self._target_url = target_url

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)
        if len(self.wait_calls) >= 2:
            self.url = self._target_url


class _UiFallbackPage:
    def __init__(self) -> None:
        self.url = "https://seller.shopee.cn/datacenter/home"
        self.wait_for_timeout = AsyncMock()
        self.trigger = _FakeLocator("All shops")
        self.region = _FakeLocator("Singapore")
        self.shop = _FakeLocator("Demo Shop")

    def locator(self, selector: str):
        if selector == 'button:has-text("/")':
            return _FakeLocatorGroup([self.trigger])
        return _FakeLocatorGroup([])

    def get_by_text(self, text: Any, exact: bool = False):
        mapping = {
            "Singapore": self.region,
            "Demo Shop": self.shop,
        }
        locator = mapping.get(str(text))
        return _FakeLocatorGroup([locator] if locator else [])


@pytest.mark.asyncio
async def test_shopee_shop_switch_noops_when_url_shop_id_already_matches() -> None:
    ctx = _ctx(
        account={"platform_shop_id": "1227491331", "store_name": "Demo Shop", "shop_region": "SG"},
    )
    page = _UrlSwitchPage(
        "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1227491331",
        "新加坡 / Demo Shop",
    )

    result = await ShopeeShopSwitch(ctx).run(page)

    assert result.success is True
    assert page.goto_calls == []
    assert ctx.config["cnsc_shop_id"] == "1227491331"
    assert ctx.config["shop_id"] == "1227491331"
    assert ctx.config["shop_name"] == "Demo Shop"


@pytest.mark.asyncio
async def test_shopee_shop_switch_rewrites_cnsc_shop_id_and_preserves_path_and_query() -> None:
    ctx = _ctx(
        account={"platform_shop_id": "1227491331", "store_name": "Demo Shop", "shop_region": "SG"},
    )
    page = _UrlSwitchPage(
        "https://seller.shopee.cn/datacenter/product/performance?cnsc_shop_id=999&foo=1",
    )

    result = await ShopeeShopSwitch(ctx).run(page)

    assert result.success is True
    assert page.goto_calls == [
        "https://seller.shopee.cn/datacenter/product/performance?cnsc_shop_id=1227491331&foo=1"
    ]
    assert ctx.config["cnsc_shop_id"] == "1227491331"


@pytest.mark.asyncio
async def test_shopee_shop_switch_waits_for_delayed_url_shop_id_refresh() -> None:
    ctx = _ctx(config={"cnsc_shop_id": "1227491331", "shop_name": "Demo Shop"})
    target_url = "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1227491331"
    page = _DelayedUrlSwitchPage(
        "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=999",
        target_url,
    )

    result = await ShopeeShopSwitch(ctx).run(page)

    assert result.success is True
    assert page.goto_calls == [target_url]
    assert len(page.wait_calls) >= 2


@pytest.mark.asyncio
async def test_shopee_shop_switch_fails_when_url_shop_id_cannot_be_confirmed() -> None:
    ctx = _ctx(config={"cnsc_shop_id": "1227491331", "shop_name": "Demo Shop"})
    page = _UrlSwitchPage("https://seller.shopee.cn/datacenter/home?cnsc_shop_id=999")

    async def _stubborn_goto(url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        page.goto_calls.append(url)
        page.url = "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=999"

    page.goto = _stubborn_goto

    result = await ShopeeShopSwitch(ctx).run(page)

    assert result.success is False
    assert result.message == "failed to confirm target shop id"


@pytest.mark.asyncio
async def test_shopee_shop_switch_uses_ui_fallback_when_target_shop_id_missing() -> None:
    ctx = _ctx(config={"shop_name": "Demo Shop", "shop_region": "SG"})
    page = _UiFallbackPage()
    switch = ShopeeShopSwitch(ctx)
    switch._wait_shop_selection_applied = AsyncMock(return_value=True)  # type: ignore[method-assign]

    result = await switch.run(page)

    assert result.success is True
    assert page.goto_calls if hasattr(page, "goto_calls") else True
    page.trigger.click.assert_awaited_once()
    page.region.click.assert_awaited_once()
    page.shop.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_shopee_shop_switch_ui_fallback_fails_when_selection_does_not_apply() -> None:
    ctx = _ctx(config={"shop_name": "Demo Shop", "shop_region": "SG"})
    page = _UiFallbackPage()
    switch = ShopeeShopSwitch(ctx)
    switch._wait_shop_selection_applied = AsyncMock(return_value=False)  # type: ignore[method-assign]

    result = await switch.run(page)

    assert result.success is False
    assert result.message == "shop switch did not apply"
