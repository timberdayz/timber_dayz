from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult
from modules.components.export.base import ExportResult
from modules.platforms.tiktok.components.analytics_export import TiktokAnalyticsExport


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account={
            "label": "acc",
            "username": "acc@example.com",
            "store_name": "Tiktok 2店",
            "shop_region": "SG",
        },
        logger=None,
        config=config or {"shop_region": "SG", "granularity": "monthly"},
    )


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.wait_calls: list[int] = []
        self.redirect_to_login = False
        self.visible_selectors: set[str] = set()
        self.visible_texts: set[str] = set()

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        if self.redirect_to_login:
            self.url = "https://seller.tiktokshopglobalselling.com/account/login"
        else:
            self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def locator(self, selector: str):
        return _FakeLocator(visible=selector in self.visible_selectors)

    def get_by_text(self, text: str, exact: bool = False):
        return _FakeLocator(visible=text in self.visible_texts)


class _FakeLocator:
    def __init__(self, *, visible: bool = False) -> None:
        self._visible = visible

    @property
    def first(self):
        return self

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def count(self) -> int:
        return 1 if self._visible else 0


def test_tiktok_analytics_export_detects_analytics_page_url() -> None:
    component = TiktokAnalyticsExport(_ctx())

    assert component._analytics_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG"
    ) is True
    assert component._analytics_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ) is False


@pytest.mark.asyncio
async def test_tiktok_analytics_export_navigates_to_analytics_page_and_runs_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    component = TiktokAnalyticsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/analytics.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG"
    ]
    switch_mock.assert_awaited_once()
    date_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    export_mock.assert_awaited_once()
    assert result.success is True
    assert result.file_path == "temp/analytics.xlsx"


@pytest.mark.asyncio
async def test_tiktok_analytics_export_returns_login_required_when_entry_state_is_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    page.visible_selectors.add("input[type='password']")
    component = TiktokAnalyticsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock()
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is False
    assert result.message == "login required before analytics export"
    switch_mock.assert_not_awaited()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_analytics_export_forwards_explicit_custom_range_to_date_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG")
    component = TiktokAnalyticsExport(
        _ctx(
            {
                "shop_region": "SG",
                "granularity": "monthly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-02-02",
                    "end_date": "2026-03-30",
                },
            }
        )
    )

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/analytics.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    date_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    export_mock.assert_awaited_once()
    assert result.success is True
