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

    assert (
        component._summary_matches(
            "57天: 2026/02/02 - 2026/03/30",
            start_date="2026-02-02",
            end_date="2026-03-30",
        )
        is True
    )


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_uses_left_page_for_start_and_right_page_for_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(
        component,
        "_read_visible_months",
        AsyncMock(return_value=((2026, 3), (2026, 4))),
        raising=False,
    )
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_navigate_right_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_right", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.LAST_7_DAYS)

    assert result.success is True
    component._navigate_left_to_month.assert_awaited_once_with(page, 2026, 3)
    component._navigate_right_to_month.assert_awaited_once_with(page, 2026, 4)
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
    monkeypatch.setattr(
        component,
        "_read_visible_months",
        AsyncMock(return_value=((2026, 4), (2026, 4))),
        raising=False,
    )
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_navigate_right_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_right", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=True), raising=False)

    result = await component.run(page, DateOption.TODAY_REALTIME)

    assert result.success is True
    component._select_start_day_on_left.assert_awaited_once_with(page, 2)
    component._select_end_day_on_right.assert_awaited_once_with(page, 2)


@pytest.mark.asyncio
async def test_tiktok_date_picker_products_run_fails_when_summary_confirmation_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokDatePicker(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")

    monkeypatch.setattr(component, "_open_panel", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_current_summary_text", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(
        component,
        "_read_visible_months",
        AsyncMock(return_value=((2026, 3), (2026, 4))),
        raising=False,
    )
    monkeypatch.setattr(component, "_navigate_left_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_navigate_right_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_start_day_on_left", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_end_day_on_right", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_confirm_range_applied", AsyncMock(return_value=False), raising=False)

    result = await component.run(page, DateOption.LAST_30_DAYS)

    assert result.success is False
    assert result.message == "failed to confirm date range"
