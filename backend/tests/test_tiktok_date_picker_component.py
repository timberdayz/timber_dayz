from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

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


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.timeout_calls: list[int] = []

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)


class _PanelLocator:
    def __init__(self, page: "_PanelPage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "_PanelLocator":
        return self

    async def count(self) -> int:
        return 1 if self.page.is_visible(self.selector) else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.page.is_visible(self.selector)

    async def click(self, timeout: int | None = None) -> None:
        self.page.clicked_selectors.append(self.selector)
        if self.selector in self.page.trigger_selectors:
            self.page.panel_opened = True


class _PanelPage(_FakePage):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.panel_opened = False
        self.clicked_selectors: list[str] = []
        self.trigger_selectors = {
            "div.theme-arco-picker.theme-arco-picker-range",
        }
        self.shortcut_selectors = {
            "[data-testid='time-selector-last-7-days']",
            "[data-testid='time-selector-last-28-days']",
        }

    def is_visible(self, selector: str) -> bool:
        if selector in self.trigger_selectors:
            return True
        if selector in self.shortcut_selectors:
            return self.panel_opened
        return False

    def locator(self, selector: str) -> _PanelLocator:
        return _PanelLocator(self, selector)


class _HeaderTextLocator:
    def __init__(self, text: str, *, visible: bool = True) -> None:
        self._text = text
        self._visible = visible

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1 if self._visible else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def inner_text(self) -> str:
        return self._text

    async def text_content(self) -> str:
        return self._text


class _HeaderLocatorGroup:
    def __init__(self, locators: list[object]) -> None:
        self._locators = locators

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int):
        return self._locators[idx]


class _CandidatePanel:
    def __init__(self, text: str, *, visible: bool = True, header_count: int = 1, cell_count: int = 31) -> None:
        self._text = text
        self._visible = visible
        self._header_count = header_count
        self._cell_count = cell_count

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def count(self) -> int:
        return 1 if self._visible else 0

    async def inner_text(self) -> str:
        return self._text

    async def text_content(self) -> str:
        return self._text

    def locator(self, selector: str):
        if selector in ('[class*="header-value"]', '[class*="picker-header"]', '[class*="header-view"]'):
            return _HeaderLocatorGroup([_HeaderTextLocator(self._text) for _ in range(self._header_count)])
        if selector in ('[class*="picker-cell"]', '[class*="cell-in-view"]', '.arco-picker-cell-in-view'):
            return _HeaderLocatorGroup([_HeaderTextLocator(str(i)) for i in range(self._cell_count)])
        raise AssertionError(f"unexpected candidate selector: {selector}")


class _FakePanelScope:
    def __init__(self, text: str) -> None:
        self._text = text

    async def is_visible(self, timeout: int | None = None) -> bool:
        return True

    async def count(self) -> int:
        return 1

    async def inner_text(self) -> str:
        return self._text

    async def text_content(self) -> str:
        return self._text

    def locator(self, selector: str):
        if selector in (
            '[class*="picker-header"]',
            '[class*="header-view"]',
            '[class*="header-value"]',
        ):
            return _HeaderTextLocator(self._text)
        raise AssertionError(f"unexpected panel selector: {selector}")

    def get_by_text(self, pattern, exact: bool = False):
        return _HeaderLocatorGroup([])


class _SplitHeaderPage(_FakePage):
    def __init__(self) -> None:
        super().__init__("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
        self._panels = [
            _FakePanelScope("2026 year 3 month"),
            _FakePanelScope("2026 year 4 month"),
        ]

    def locator(self, selector: str):
        if selector in (
            ".theme-arco-picker-panel",
            ".arco-picker-panel",
            '[class*="picker-panel"]',
            '.arco-picker-range-wrapper > *',
            '.arco-picker-range-container > *',
            '[class*="picker-range-wrapper"] > *',
            '[class*="picker-range-container"] > *',
        ):
            return _HeaderLocatorGroup(self._panels)
        raise AssertionError(f"unexpected selector: {selector}")


class _PanelSelectionPage(_FakePage):
    def __init__(self) -> None:
        super().__init__("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
        self._candidates = [
            _CandidatePanel("2026 year 3 month 2026 year 4 month", header_count=2, cell_count=62),
            _CandidatePanel("2026 year 3 month", header_count=1, cell_count=31),
            _CandidatePanel("2026 year 4 month", header_count=1, cell_count=31),
        ]

    def locator(self, selector: str):
        if selector in (
            ".theme-arco-picker-panel",
            ".arco-picker-panel",
            '[class*="picker-panel"]',
            '.arco-picker-range-wrapper > *',
            '.arco-picker-range-container > *',
            '[class*="picker-range-wrapper"] > *',
            '[class*="picker-range-container"] > *',
        ):
            return _HeaderLocatorGroup(self._candidates)
        raise AssertionError(f"unexpected selector: {selector}")


class _DuplicatePanelSelectionPage(_FakePage):
    def __init__(self) -> None:
        super().__init__("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
        self.left = _CandidatePanel("2026 year 3 month", header_count=1, cell_count=31)
        self.right = _CandidatePanel("2026 year 4 month", header_count=1, cell_count=31)

    def locator(self, selector: str):
        if selector in ('.arco-picker-range-wrapper > *', '.arco-picker-range-container > *'):
            return _HeaderLocatorGroup([self.left, self.right])
        if selector in (
            ".theme-arco-picker-panel",
            ".arco-picker-panel",
            '[class*="picker-panel"]',
            '[class*="picker-range-wrapper"] > *',
            '[class*="picker-range-container"] > *',
        ):
            return _HeaderLocatorGroup([self.left, self.right, self.left, self.right])
        raise AssertionError(f"unexpected selector: {selector}")


class _RangeInput:
    def __init__(self, value: str) -> None:
        self._value = value

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self, timeout: int | None = None) -> bool:
        return True

    async def input_value(self) -> str:
        return self._value

    async def text_content(self) -> str:
        return ""

    async def inner_text(self) -> str:
        return ""


class _RangeContainer:
    def __init__(self, start_value: str, end_value: str, prefix_text: str) -> None:
        self._start = _RangeInput(start_value)
        self._end = _RangeInput(end_value)
        self._prefix = prefix_text

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self, timeout: int | None = None) -> bool:
        return True

    async def text_content(self) -> str:
        return f"{self._prefix}-"

    async def inner_text(self) -> str:
        return f"{self._prefix}-"

    def locator(self, selector: str):
        if selector == ".arco-picker-input":
            return _HeaderLocatorGroup([self._start, self._end])
        if selector == "input":
            return _HeaderLocatorGroup([self._start, self._end])
        raise AssertionError(f"unexpected range selector: {selector}")


class _NavButton:
    def __init__(self, name: str) -> None:
        self.name = name
        self.clicked = 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return True

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1

    async def inner_text(self) -> str:
        return self.name

    async def inner_html(self) -> str:
        mapping = {
            "year-prev": '<svg class="arco-icon arco-icon-double_left"></svg>',
            "month-prev": '<svg class="arco-icon arco-icon-left"></svg>',
            "month-next": '<svg class="arco-icon arco-icon-right"></svg>',
            "year-next": '<svg class="arco-icon arco-icon-double_right"></svg>',
        }
        return mapping[self.name]


class _NavButtonsScope:
    def __init__(self, buttons: list[_NavButton]) -> None:
        self.buttons = buttons

    def locator(self, selector: str):
        if selector == '.arco-picker-header-icon:has(svg.arco-icon-left)':
            return _HeaderLocatorGroup([button for button in self.buttons if button.name == "month-prev"])
        if selector == '.arco-picker-header-icon:has(svg.arco-icon-right)':
            return _HeaderLocatorGroup([button for button in self.buttons if button.name == "month-next"])
        if selector == '[class*="picker-header-icon"]:has(svg[class~="arco-icon-left"])':
            return _HeaderLocatorGroup([button for button in self.buttons if button.name == "month-prev"])
        if selector == '[class*="picker-header-icon"]:has(svg[class~="arco-icon-right"])':
            return _HeaderLocatorGroup([button for button in self.buttons if button.name == "month-next"])
        if selector in (
            ".arco-picker-header-icon:not(.arco-picker-header-icon-hidden)",
            '[class*="picker-header-icon"]:not([class*="hidden"])',
            'button[class*="header-icon"]:not([class*="hidden"])',
        ):
            return _HeaderLocatorGroup(self.buttons)
        raise AssertionError(f"unexpected nav scope selector: {selector}")


class _NavButtonsPage(_FakePage):
    def __init__(self) -> None:
        super().__init__("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
        self.left_buttons = [
            _NavButton("year-prev"),
            _NavButton("month-prev"),
        ]
        self.right_buttons = [
            _NavButton("month-next"),
            _NavButton("year-next"),
        ]

    async def panel_scope(self, pane: str):
        return _NavButtonsScope(self.left_buttons if pane == "left" else self.right_buttons)


class _SummaryPage(_FakePage):
    def __init__(self) -> None:
        super().__init__("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
        self._range = _RangeContainer("2026/03/01", "2026/03/31", "31 days")

    def locator(self, selector: str):
        if selector in (
            '#page-title-datepicker [data-tid="m4b_date_picker_range_picker"]',
            '[data-tid="m4b_date_picker_range_picker"]',
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            "div.theme-arco-picker-range",
            "div.arco-picker-range",
            "div.theme-arco-picker",
            "div.arco-picker",
            "div.theme-arco-picker-input",
            "div.arco-picker-input",
        ):
            return self._range
        raise AssertionError(f"unexpected summary selector: {selector}")


def test_tiktok_date_picker_resolve_range_maps_today_to_same_day() -> None:
    component = TiktokDatePicker(_ctx())
    start_date, end_date = component._resolve_range(DateOption.TODAY_REALTIME, today=date(2026, 4, 2))
    assert start_date == "2026-04-02"
    assert end_date == "2026-04-02"


def test_tiktok_date_picker_resolve_range_maps_yesterday_to_previous_day() -> None:
    component = TiktokDatePicker(_ctx())
    start_date, end_date = component._resolve_range(DateOption.YESTERDAY, today=date(2026, 4, 2))
    assert start_date == "2026-04-01"
    assert end_date == "2026-04-01"


def test_tiktok_date_picker_resolve_range_maps_last_7_days_to_shopee_aligned_window() -> None:
    component = TiktokDatePicker(_ctx())
    start_date, end_date = component._resolve_range(DateOption.LAST_7_DAYS, today=date(2026, 4, 2))
    assert start_date == "2026-03-27"
    assert end_date == "2026-04-02"


def test_tiktok_date_picker_resolve_range_maps_last_30_days_to_shopee_aligned_window() -> None:
    component = TiktokDatePicker(_ctx())
    start_date, end_date = component._resolve_range(DateOption.LAST_30_DAYS, today=date(2026, 4, 2))
    assert start_date == "2026-03-04"
    assert end_date == "2026-04-02"


def test_tiktok_date_picker_summary_match_accepts_collapsed_range_text() -> None:
    component = TiktokDatePicker(_ctx())
    assert component._summary_matches(
        "57 days 2026/02/02 - 2026/03/30",
        start_date="2026-02-02",
        end_date="2026-03-30",
    ) is True


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_uses_left_page_for_start_and_right_page_for_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(component, "_resolve_range", lambda option, today=None: ("2026-03-27", "2026-04-02"), raising=False)
    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_read_visible_months", AsyncMock(return_value=((2026, 3), (2026, 4))), raising=False)
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_navigate_right_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_right", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.LAST_7_DAYS)

    assert result.success is True
    component._navigate_left_to_month.assert_awaited_once_with(page, 2026, 3)
    component._select_start_day_on_left.assert_awaited_once_with(page, 27)
    component._select_end_day_on_right.assert_awaited_once_with(page, 2)


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_still_uses_left_start_right_end_for_same_day_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(component, "_resolve_range", lambda option, today=None: ("2026-04-02", "2026-04-02"), raising=False)
    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_read_visible_months", AsyncMock(return_value=((2026, 4), (2026, 4))), raising=False)
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.TODAY_REALTIME)

    assert result.success is True
    component._navigate_left_to_month.assert_awaited_once_with(page, 2026, 4)
    component._select_start_day_on_left.assert_awaited_once_with(page, 2)
    component._select_end_day_on_left.assert_awaited_once_with(page, 2)


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_keeps_same_month_range_on_left_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_resolve_range",
        lambda option, today=None: ("2026-03-01", "2026-03-31"),
        raising=False,
    )
    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_read_visible_months", AsyncMock(return_value=((2026, 3), (2026, 4))), raising=False)
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.LAST_30_DAYS)

    assert result.success is True
    component._navigate_left_to_month.assert_awaited_once_with(page, 2026, 3)
    component._select_start_day_on_left.assert_awaited_once_with(page, 1)
    component._select_end_day_on_left.assert_awaited_once_with(page, 31)


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_continues_after_navigation_fallback_hits_target_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_resolve_range",
        lambda option, today=None: ("2025-12-01", "2025-12-31"),
        raising=False,
    )
    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.LAST_30_DAYS)

    assert result.success is True
    component._select_start_day_on_left.assert_awaited_once_with(page, 1)
    component._select_end_day_on_left.assert_awaited_once_with(page, 31)


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_fails_when_summary_confirmation_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_read_visible_months", AsyncMock(return_value=((2026, 3), (2026, 4))), raising=False)
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_navigate_right_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_right", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=False), raising=False)

    result = await component.run(page, DateOption.LAST_30_DAYS)

    assert result.success is False
    assert result.message == "failed to confirm date range"


@pytest.mark.asyncio
async def test_tiktok_date_picker_open_panel_treats_visible_shortcuts_as_panel_open() -> None:
    component = TiktokDatePicker(_ctx())
    page = _PanelPage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    opened = await component._open_panel(page)

    assert opened is True
    assert page.clicked_selectors == ["div.theme-arco-picker.theme-arco-picker-range"]


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_left_month_uses_shared_prev_arrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(side_effect=[(2026, 3), (2026, 2), (2026, 2)]),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=(2026, 2)),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_left_to_month(page, 2026, 2)

    assert result is True
    click_nav.assert_awaited_once_with(page, "prev")


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_right_month_uses_shared_next_arrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(side_effect=[(2026, 3), (2026, 4), (2026, 4)]),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=(2026, 4)),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_right_to_month(page, 2026, 4)

    assert result is True
    click_nav.assert_awaited_once_with(page, "next")


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_left_month_fails_when_header_never_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(return_value=(2025, 11)),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=None),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_left_to_month(page, 2025, 12)

    assert result is False
    click_nav.assert_awaited_once_with(page, "next")


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_left_month_accepts_target_after_change_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(side_effect=[(2025, 11), (2025, 12), (2025, 12)]),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=None),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_left_to_month(page, 2025, 12)

    assert result is True
    click_nav.assert_awaited_once_with(page, "next")


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_right_month_accepts_target_after_change_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(side_effect=[(2025, 12), (2026, 1), (2026, 1)]),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=None),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_right_to_month(page, 2026, 1)

    assert result is True
    click_nav.assert_awaited_once_with(page, "next")


@pytest.mark.asyncio
async def test_tiktok_date_picker_navigate_left_month_accepts_target_during_stability_retry_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(
        component,
        "_current_pane_month",
        AsyncMock(side_effect=[(2025, 11), (2025, 11), (2025, 12), (2025, 12)]),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_pane_month_changed",
        AsyncMock(return_value=None),
        raising=False,
    )
    click_nav = AsyncMock(return_value=True)
    monkeypatch.setattr(component, "_click_month_nav", click_nav, raising=False)

    result = await component._navigate_left_to_month(page, 2025, 12)

    assert result is True
    click_nav.assert_awaited_once_with(page, "next")


@pytest.mark.asyncio
async def test_tiktok_date_picker_reads_split_month_headers_from_visible_panel_text() -> None:
    component = TiktokDatePicker(_ctx())
    page = _SplitHeaderPage()

    left_month, right_month = await component._read_visible_months(page)

    assert left_month == (2026, 3)
    assert right_month == (2026, 4)


@pytest.mark.asyncio
async def test_tiktok_date_picker_panel_scope_prefers_single_header_calendar_panels() -> None:
    component = TiktokDatePicker(_ctx())
    page = _PanelSelectionPage()

    left_scope = await component._panel_scope(page, "left")
    right_scope = await component._panel_scope(page, "right")

    assert await left_scope.inner_text() == "2026 year 3 month"
    assert await right_scope.inner_text() == "2026 year 4 month"


@pytest.mark.asyncio
async def test_tiktok_date_picker_panel_scope_deduplicates_overlapping_candidates() -> None:
    component = TiktokDatePicker(_ctx())
    page = _DuplicatePanelSelectionPage()

    left_scope = await component._panel_scope(page, "left")
    right_scope = await component._panel_scope(page, "right")

    assert await left_scope.inner_text() == "2026 year 3 month"
    assert await right_scope.inner_text() == "2026 year 4 month"


@pytest.mark.asyncio
async def test_tiktok_date_picker_current_summary_text_reads_range_input_values() -> None:
    component = TiktokDatePicker(_ctx())
    page = _SummaryPage()

    summary = await component._current_summary_text(page)

    assert "2026/03/01" in summary
    assert "2026/03/31" in summary


@pytest.mark.asyncio
async def test_tiktok_date_picker_click_month_nav_ignores_year_buttons() -> None:
    component = TiktokDatePicker(_ctx())
    page = _NavButtonsPage()

    async def _panel_scope(_page, pane: str):
        return await page.panel_scope(pane)

    component._panel_scope = _panel_scope  # type: ignore[method-assign]

    prev_ok = await component._click_month_nav(page, "prev")
    next_ok = await component._click_month_nav(page, "next")

    assert prev_ok is True
    assert next_ok is True
    assert page.left_buttons[0].clicked == 0
    assert page.left_buttons[1].clicked == 1
    assert page.right_buttons[0].clicked == 1
    assert page.right_buttons[1].clicked == 0
