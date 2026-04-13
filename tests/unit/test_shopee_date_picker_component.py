from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker


class _FakePage:
    async def wait_for_timeout(self, _ms: int) -> None:
        return None


class _FakeTextLocator:
    def __init__(self, text: str, *, visible: bool = True) -> None:
        self._text = text
        self._visible = visible
        self.clicked = False
        self.hovered = False

    async def count(self) -> int:
        return 1

    async def is_visible(self, *args, **kwargs) -> bool:
        return self._visible

    async def text_content(self) -> str:
        return self._text

    async def click(self, *args, **kwargs) -> None:
        self.clicked = True

    async def hover(self, *args, **kwargs) -> None:
        self.hovered = True


class _FakeLocatorSequence:
    def __init__(self, locators: list[Any]) -> None:
        self._locators = locators

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int):
        return self._locators[idx]

    @property
    def first(self):
        return self._locators[0] if self._locators else _FakeTextLocator("", visible=False)

    @property
    def last(self):
        return self._locators[-1] if self._locators else _FakeTextLocator("", visible=False)

    def filter(self, *, has_text: str | None = None):
        if not has_text:
            return self
        return _FakeLocatorSequence(
            [locator for locator in self._locators if has_text in getattr(locator, "_text", "")]
        )


class _DatePanelPage(_FakePage):
    def __init__(self, panels: list[_FakeTextLocator], text_map: dict[str, _FakeTextLocator] | None = None) -> None:
        self._panels = panels
        self._text_map = text_map or {}

    def locator(self, selector: str):
        if selector in (
            ".arco-trigger-popup",
            ".arco-picker-dropdown",
            ".ant-picker-dropdown",
            '[class*="picker-dropdown"]',
            '[class*="dropdown"]',
            '[class*="popup"]',
            "body > div",
            "div",
            "ul",
        ):
            return _FakeLocatorSequence(self._panels)
        return _FakeLocatorSequence([])

    def get_by_text(self, text, exact: bool = False):
        key = str(text)
        locator = self._text_map.get(key)
        if locator is None:
            return _FakeLocatorSequence([])
        return _FakeLocatorSequence([locator])


class _MonthNavPage(_FakePage):
    def __init__(self, headers: list[str]) -> None:
        self._headers = headers
        self._header_idx = 0

    def locator(self, selector: str):
        if selector == "body > div":
            return _FakeLocatorSequence([self])
        if "header" in selector:
            return _FakeLocatorSequence([_FakeTextLocator(self._headers[self._header_idx])])
        return _FakeLocatorSequence([])

    async def count(self) -> int:
        return 1

    async def is_visible(self, timeout: int = 500) -> bool:
        return True

    async def text_content(self) -> str:
        return self._headers[self._header_idx]

    def get_by_text(self, text, exact: bool = False):
        normalized = str(text)
        if normalized in {"<", "\u2039"}:
            return _FakeLocatorSequence([_FakeTextLocator(normalized)])
        if normalized in {">", "\u203a"}:
            return _FakeLocatorSequence([_NavAdvanceLocator(normalized, self._advance)])
        return _FakeLocatorSequence([])

    def _advance(self) -> None:
        if self._header_idx < len(self._headers) - 1:
            self._header_idx += 1


class _NavAdvanceLocator(_FakeTextLocator):
    def __init__(self, text: str, on_click) -> None:
        super().__init__(text)
        self._on_click = on_click

    async def click(self, *args, **kwargs) -> None:
        self.clicked = True
        self._on_click()


@pytest.mark.asyncio
async def test_shopee_date_picker_custom_weekly_uses_week_mode_delegate_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage()
    picker = ShopeeDatePicker(
        ExecutionContext(
            platform="shopee",
            account={},
            config={
                "data_domain": "services",
                "services_subtype": "agent",
                "granularity": "weekly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-05",
                },
                "start_date": "2026-03-30",
                "end_date": "2026-04-05",
            },
        )
    )

    monkeypatch.setattr(picker, "_current_date_summary_text", AsyncMock(return_value="旧范围"), raising=False)
    monkeypatch.setattr(picker, "_custom_date_summary_matches", lambda *args, **kwargs: False, raising=False)
    monkeypatch.setattr(picker, "_resolve_custom_target", lambda config: {
        "granularity": "weekly",
        "start_date": "2026-03-30",
        "end_date": "2026-04-05",
        "target_iso_date": "2026-03-30",
    }, raising=False)
    monkeypatch.setattr(picker, "_normalize_custom_granularity", lambda value: "weekly", raising=False)
    monkeypatch.setattr(picker, "_open_date_picker", AsyncMock(), raising=False)
    monkeypatch.setattr(picker, "_hover_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(picker, "_select_week_range_value", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(picker, "_wait_custom_date_selection_applied", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(
        picker._delegate,
        "_ensure_date_selection",
        AsyncMock(side_effect=AssertionError("run should not call legacy _ensure_date_selection")),
        raising=False,
    )

    result = await picker.run(page, DateOption.LAST_7_DAYS)

    assert result.success is True
    picker._open_date_picker.assert_awaited_once()
    picker._hover_text_option.assert_awaited_once_with(page, "按周")
    picker._select_week_range_value.assert_awaited_once_with(page, "2026-03-30", "2026-04-05")


@pytest.mark.asyncio
async def test_shopee_date_picker_preset_path_uses_target_label_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage()
    picker = ShopeeDatePicker(
        ExecutionContext(
            platform="shopee",
            account={},
            config={"data_domain": "analytics", "granularity": "daily", "date_preset": "yesterday"},
        )
    )

    monkeypatch.setattr(picker, "_current_date_label", AsyncMock(return_value="今天"), raising=False)
    monkeypatch.setattr(picker, "_open_date_picker", AsyncMock(), raising=False)
    monkeypatch.setattr(picker, "_click_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(picker, "_wait_date_selection_applied", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(
        picker._delegate,
        "_ensure_date_selection",
        AsyncMock(side_effect=AssertionError("run should not call legacy _ensure_date_selection")),
        raising=False,
    )

    result = await picker.run(page, DateOption.YESTERDAY)

    assert result.success is True
    picker._open_date_picker.assert_awaited_once()
    picker._click_text_option.assert_awaited_once()


@pytest.mark.asyncio
async def test_shopee_date_picker_find_date_panel_prefers_service_panel_without_today_realtime() -> None:
    picker = ShopeeDatePicker(
        ExecutionContext(
            platform="shopee",
            account={},
            config={"data_domain": "services", "services_subtype": "agent", "granularity": "weekly"},
        )
    )
    page = _DatePanelPage(
        [
            _FakeTextLocator("按日 按周 按月 昨天 过去7天 过去30天"),
            _FakeTextLocator("页面其他内容"),
        ]
    )

    panel = await picker._find_date_panel(page)

    assert panel is not None
    assert await panel.text_content() == "按日 按周 按月 昨天 过去7天 过去30天"


@pytest.mark.asyncio
async def test_shopee_date_picker_hover_text_option_uses_panel_scoped_entry() -> None:
    picker = ShopeeDatePicker(
        ExecutionContext(
            platform="shopee",
            account={},
            config={"data_domain": "services", "services_subtype": "agent", "granularity": "weekly"},
        )
    )
    option = _FakeTextLocator("按周")
    page = _FakePage()
    picker._find_date_option_locator = AsyncMock(return_value=option)  # type: ignore[method-assign]

    clicked = await picker._hover_text_option(page, "按周")

    assert clicked is True
    assert option.hovered is True
    assert option.clicked is True


@pytest.mark.asyncio
async def test_shopee_date_picker_navigate_calendar_panel_to_month_advances_until_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picker = ShopeeDatePicker(
        ExecutionContext(platform="shopee", account={}, config={"data_domain": "services", "services_subtype": "agent"})
    )
    page = _FakePage()

    monkeypatch.setattr(
        picker,
        "_current_popup_header_text",
        AsyncMock(side_effect=["\u56db\u67082025", "\u4e94\u67082025", "\u516d\u67082025", "\u4e09\u67082026"]),
        raising=False,
    )
    monkeypatch.setattr(picker, "_click_popup_month_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(
        picker,
        "_wait_calendar_header_changed",
        AsyncMock(side_effect=["\u4e94\u67082025", "\u516d\u67082025", "\u4e09\u67082026"]),
        raising=False,
    )

    result = await picker._navigate_calendar_panel_to_month(page, 2026, 3)

    assert result is True
    assert picker._click_popup_month_nav_button.await_count == 3
