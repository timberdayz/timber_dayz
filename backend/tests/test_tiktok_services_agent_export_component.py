from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult
from modules.components.export.base import ExportResult
from modules.platforms.tiktok.components.services_agent_export import TiktokServicesAgentExport


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account={
            "label": "acc",
            "username": "acc@example.com",
            "store_name": "Tiktok 2店",
            "shop_region": "MY",
        },
        logger=None,
        config=config or {"shop_region": "MY", "granularity": "monthly"},
    )


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.wait_calls: list[int] = []
        self.visible_selectors: set[str] = set()
        self.visible_texts: set[str] = set()

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
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


def test_tiktok_services_agent_export_detects_service_page_url() -> None:
    component = TiktokServicesAgentExport(_ctx())

    assert component._services_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY"
    ) is True
    assert component._services_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=MY"
    ) is False


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_navigates_to_services_page_and_runs_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/services-agent.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)
    monkeypatch.setattr(component, "_no_exportable_data", AsyncMock(return_value=False), raising=False)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY"
    ]
    switch_mock.assert_awaited_once()
    date_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    export_mock.assert_awaited_once()
    assert result.success is True
    assert result.file_path == "temp/services-agent.xlsx"


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_returns_success_when_no_exportable_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)
    monkeypatch.setattr(component, "_no_exportable_data", AsyncMock(return_value=True), raising=False)

    result = await component.run(page)

    export_mock.assert_not_awaited()
    assert result.success is True
    assert result.file_path is None
    assert "no exportable" in result.message


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_returns_login_required_when_entry_state_is_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    page.visible_selectors.add("input[type='password']")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    switch_mock = AsyncMock()
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is False
    assert result.message == "login required before services agent export"
    switch_mock.assert_not_awaited()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()
