from __future__ import annotations

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


def _ctx(
    account: dict | None = None,
    config: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account=account
        or {
            "label": "acc",
            "username": "acc",
        },
        logger=None,
        config=config or {},
    )


class _FakeLocator:
    def __init__(self, *, visible: bool = True, text: str = "") -> None:
        self.visible = visible
        self.text = text

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.visible

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def inner_text(self, timeout: int | None = None) -> str:
        return self.text

    async def all_inner_texts(self) -> list[str]:
        return [self.text] if self.text else []


class _FakePage:
    def __init__(self, url: str, store_label: str) -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.timeout_calls: list[int] = []
        self.store_label = store_label

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 20000) -> None:
        self.goto_calls.append(url)
        self.url = url
        if "shop_region=MY" in url:
            self.store_label = "MY Malaysia(Flora Mall)"
        elif "shop_region=PH" in url:
            self.store_label = "PH Philippines(DAJU Mall)"
        elif "shop_region=SG" in url:
            self.store_label = "SG Singapore(HX Home)"

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return _FakeLocator(visible=text in self.store_label, text=self.store_label)

    def locator(self, selector: str) -> _FakeLocator:
        if selector == "div[role='button']:has-text('SG'), div[role='button']:has-text('MY'), div[role='button']:has-text('PH')":
            return _FakeLocator(visible=True, text=self.store_label)
        return _FakeLocator(visible=False)


class _DelayedRefreshPage(_FakePage):
    def __init__(self, url: str, store_label: str, target_region: str) -> None:
        super().__init__(url, store_label)
        self.target_region = target_region
        self.pending_url: str | None = None
        self.pending_label: str | None = None

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 20000) -> None:
        self.goto_calls.append(url)
        self.pending_url = url
        if self.target_region == "PH":
            self.pending_label = "PH Philippines(DAJU Mall)"
        elif self.target_region == "MY":
            self.pending_label = "MY Malaysia(Flora Mall)"
        else:
            self.pending_label = "SG Singapore(HX Home)"

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)
        if len(self.timeout_calls) >= 2 and self.pending_url:
            self.url = self.pending_url
            self.store_label = self.pending_label or self.store_label


@pytest.mark.asyncio
async def test_tiktok_shop_switch_syncs_current_region_and_display_name_from_page() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={},
    )
    page = _FakePage(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=PH",
        "PH Philippines(DAJU Mall)",
    )

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is True
    assert ctx.config["shop_region"] == "PH"
    assert ctx.config["shop_name"] == "acc_ph"
    assert ctx.config["shop_display_name"] == "PH Philippines(DAJU Mall)"
    assert page.goto_calls == []


@pytest.mark.asyncio
async def test_tiktok_shop_switch_rewrites_only_shop_region_and_preserves_path_and_query() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={"shop_region": "MY"},
    )
    page = _FakePage(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG&foo=1",
        "SG Singapore(HX Home)",
    )

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is True
    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=MY&foo=1"
    ]
    assert ctx.config["shop_region"] == "MY"
    assert ctx.config["shop_name"] == "acc_my"
    assert ctx.config["shop_display_name"] == "MY Malaysia(Flora Mall)"


@pytest.mark.asyncio
async def test_tiktok_shop_switch_fails_when_region_cannot_be_confirmed_after_navigation() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={"shop_region": "MY"},
    )
    page = _FakePage(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG",
        "SG Singapore(HX Home)",
    )

    async def _stubborn_goto(url: str, wait_until: str = "domcontentloaded", timeout: int = 20000) -> None:
        page.goto_calls.append(url)
        page.url = "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
        page.store_label = "SG Singapore(HX Home)"

    page.goto = _stubborn_goto

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is False
    assert result.message == "failed to confirm target shop region"


@pytest.mark.asyncio
async def test_tiktok_shop_switch_fails_when_visible_store_display_disagrees_with_region() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={"shop_region": "MY"},
    )
    page = _FakePage(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY",
        "SG Singapore(HX Home)",
    )

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is False
    assert result.message == "failed to confirm target shop region"


@pytest.mark.asyncio
async def test_tiktok_shop_switch_allows_missing_display_name_when_url_region_is_already_correct() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={"shop_region": "SG"},
    )
    page = _FakePage(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG",
        "",
    )

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is True
    assert result.region == "SG"
    assert ctx.config["shop_region"] == "SG"
    assert ctx.config["shop_name"] == "acc_sg"
    assert "shop_display_name" not in ctx.config


@pytest.mark.asyncio
async def test_tiktok_shop_switch_waits_for_delayed_region_refresh_before_confirming() -> None:
    ctx = _ctx(
        account={"label": "acc"},
        config={"shop_region": "PH"},
    )
    page = _DelayedRefreshPage(
        "https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=SG",
        "SG Singapore(HX Home)",
        "PH",
    )

    result = await TiktokShopSwitch(ctx).run(page)

    assert result.success is True
    assert ctx.config["shop_region"] == "PH"
    assert ctx.config["shop_display_name"] == "PH Philippines(DAJU Mall)"
    assert len(page.timeout_calls) >= 2
