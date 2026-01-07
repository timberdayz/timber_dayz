from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.tiktok.components.navigation import TiktokNavigation


class FakePage:
    def __init__(self) -> None:
        self.captured_url: str | None = None

    # Simulate Playwright Page.goto
    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 45000) -> None:  # noqa: FBT001, FBT002
        self.captured_url = url

    # Simulate small sleep
    def wait_for_timeout(self, ms: int) -> None:  # noqa: ARG002
        return


def make_ctx(config: dict[str, Any] | None = None) -> ExecutionContext:
    account = {"shop_region": "SG", "login_url": "https://seller.tiktokglobalshop.com"}
    return ExecutionContext(platform="tiktok", account=account, config=config or {})


def test_traffic_overview_omits_time_params_by_default() -> None:
    page = FakePage()
    ctx = make_ctx()
    nav = TiktokNavigation(ctx)

    res = nav.run(page, TargetPage.TRAFFIC_OVERVIEW)
    assert res.success is True
    assert isinstance(page.captured_url, str)
    assert "timeRange=" not in page.captured_url
    assert "shortcut=" not in page.captured_url
    assert "shop_region=" in page.captured_url


def test_products_includes_time_params_by_default() -> None:
    page = FakePage()
    ctx = make_ctx()
    nav = TiktokNavigation(ctx)

    res = nav.run(page, TargetPage.PRODUCTS_PERFORMANCE)
    assert res.success is True
    assert isinstance(page.captured_url, str)
    assert "timeRange=" in page.captured_url
    assert "shortcut=" in page.captured_url
    assert "shop_region=" in page.captured_url


def test_override_nav_with_timerange_true_for_traffic() -> None:
    page = FakePage()
    ctx = make_ctx({"nav_with_timerange": True})
    nav = TiktokNavigation(ctx)

    res = nav.run(page, TargetPage.TRAFFIC_OVERVIEW)
    assert res.success is True
    assert isinstance(page.captured_url, str)
    assert "timeRange=" in page.captured_url  # explicit override respected
    assert "shortcut=" in page.captured_url


def test_override_nav_with_timerange_false_for_products() -> None:
    page = FakePage()
    ctx = make_ctx({"nav_with_timerange": False})
    nav = TiktokNavigation(ctx)

    res = nav.run(page, TargetPage.PRODUCTS_PERFORMANCE)
    assert res.success is True
    assert isinstance(page.captured_url, str)
    assert "timeRange=" not in page.captured_url  # explicit override respected
    assert "shortcut=" not in page.captured_url

