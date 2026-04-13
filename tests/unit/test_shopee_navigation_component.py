from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.navigation import ShopeeNavigation


class _FakePage:
    def __init__(self, url: str = "") -> None:
        self.url = url
        self.goto = AsyncMock(side_effect=self._goto)
        self.wait_for_timeout = AsyncMock()

    async def _goto(self, url: str, **kwargs) -> None:
        self.url = url


@pytest.mark.asyncio
async def test_shopee_navigation_noops_when_overview_already_ready() -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/performance")
    nav = ShopeeNavigation(ExecutionContext(platform="shopee", account={}, config={}))

    await nav.ensure_overview_ready(
        page,
        overview_path="/datacenter/product/performance",
        error_message="products page is not ready",
    )

    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_navigation_goto_target_when_not_ready() -> None:
    page = _FakePage("https://seller.shopee.cn/seller/home")
    nav = ShopeeNavigation(ExecutionContext(platform="shopee", account={}, config={}))

    await nav.ensure_overview_ready(
        page,
        overview_path="/datacenter/product/performance",
        error_message="products page is not ready",
    )

    page.goto.assert_awaited_once()
    assert "/datacenter/product/performance" in page.url


@pytest.mark.asyncio
async def test_shopee_navigation_requires_business_ready_probe_when_provided() -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/traffic/overview")
    nav = ShopeeNavigation(ExecutionContext(platform="shopee", account={}, config={}))
    probe = AsyncMock(return_value=False)

    with pytest.raises(RuntimeError, match="analytics business not ready"):
        await nav.ensure_overview_ready(
            page,
            overview_path="/datacenter/traffic/overview",
            error_message="analytics page is not ready",
            business_ready=probe,
            business_error_message="analytics business not ready",
        )
