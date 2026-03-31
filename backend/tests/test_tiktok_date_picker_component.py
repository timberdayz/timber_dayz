from __future__ import annotations

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.platforms.tiktok.components.date_picker import TiktokDatePicker


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account={"label": "acc", "shop_region": "SG"},
        logger=None,
        config=config or {},
    )


class _FakeLocator:
    def __init__(self, *, visible: bool = False, on_click=None) -> None:
        self.visible = visible
        self.clicked = 0
        self._on_click = on_click

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.visible

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1
        if self._on_click:
            self._on_click()


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.timeout_calls: list[int] = []
        self.locators: dict[str, _FakeLocator] = {}

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)

    def locator(self, selector: str) -> _FakeLocator:
        return self.locators.get(selector, _FakeLocator())


def _build_shared_picker_page(url: str, quick_selector: str) -> tuple[_FakePage, _FakeLocator, _FakeLocator]:
    page = _FakePage(url)
    panel = _FakeLocator(visible=False)

    def _open_panel() -> None:
        panel.visible = True
        quick.visible = True

    def _pick_quick() -> None:
        panel.visible = False

    trigger = _FakeLocator(visible=True, on_click=_open_panel)
    quick = _FakeLocator(visible=False, on_click=_pick_quick)

    page.locators["div.theme-arco-picker.theme-arco-picker-range"] = trigger
    page.locators[".theme-arco-picker-dropdown"] = panel
    page.locators[quick_selector] = quick
    return page, trigger, quick


@pytest.mark.asyncio
async def test_tiktok_date_picker_opens_panel_and_applies_last_7_days_for_traffic() -> None:
    component = TiktokDatePicker(_ctx())
    page, trigger, quick = _build_shared_picker_page(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG",
        "[data-testid='time-selector-last-7-days']",
    )

    result = await component.run(page, DateOption.LAST_7_DAYS)

    assert result.success is True
    assert trigger.clicked == 1
    assert quick.clicked == 1


@pytest.mark.asyncio
async def test_tiktok_date_picker_applies_last_28_days_for_products() -> None:
    component = TiktokDatePicker(_ctx())
    page, trigger, quick = _build_shared_picker_page(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG",
        "[data-testid='time-selector-last-28-days']",
    )

    result = await component.run(page, DateOption.LAST_28_DAYS)

    assert result.success is True
    assert trigger.clicked == 1
    assert quick.clicked == 1


@pytest.mark.asyncio
async def test_tiktok_date_picker_applies_last_7_days_for_service_analytics() -> None:
    component = TiktokDatePicker(_ctx())
    page, trigger, quick = _build_shared_picker_page(
        "https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=SG",
        "button:has-text(\"近7天\")",
    )
    page.locators["button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn"] = trigger

    result = await component.run(page, DateOption.LAST_7_DAYS)

    assert result.success is True
    assert trigger.clicked == 1
    assert quick.clicked == 1


@pytest.mark.asyncio
async def test_tiktok_date_picker_applies_last_28_days_for_service_analytics() -> None:
    component = TiktokDatePicker(_ctx())
    page, trigger, quick = _build_shared_picker_page(
        "https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=SG",
        "button:has-text(\"近28天\")",
    )
    page.locators["button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn"] = trigger

    result = await component.run(page, DateOption.LAST_28_DAYS)

    assert result.success is True
    assert trigger.clicked == 1
    assert quick.clicked == 1
