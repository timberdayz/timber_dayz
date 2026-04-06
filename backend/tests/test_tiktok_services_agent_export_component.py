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
        self.custom_locators: dict[str, object] = {}

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def locator(self, selector: str):
        if selector in self.custom_locators:
            return self.custom_locators[selector]
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

    async def get_attribute(self, name: str) -> str | None:
        return None


class _AttrLocator(_FakeLocator):
    def __init__(self, *, visible: bool = True, attrs: dict[str, str | None] | None = None) -> None:
        super().__init__(visible=visible)
        self._attrs = attrs or {}

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)


class _TabLocator:
    def __init__(self, page: "_TabPage", selector: str, *, visible: bool = True) -> None:
        self._page = page
        self._selector = selector
        self._visible = visible

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1 if self._visible else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def click(self, timeout: int | None = None) -> None:
        self._page.clicked_selectors.append(self._selector)
        if "聊天详情" in self._selector:
            self._page.detail_selected = True
            self._page.loading_visible = True

    async def scroll_into_view_if_needed(self, timeout: int | None = None) -> None:
        return None

    async def get_attribute(self, name: str) -> str | None:
        if name == "aria-selected":
            if "聊天详情" in self._selector:
                return "true" if self._page.detail_selected else "false"
            if "聊天概览" in self._selector:
                return "false" if self._page.detail_selected else "true"
            return "false"
        if name == "class":
            if self._page.detail_selected and "聊天详情" in self._selector:
                return "theme-arco-tabs-header-title theme-arco-tabs-header-title-active"
            if not self._page.detail_selected and "聊天概览" in self._selector:
                return "theme-arco-tabs-header-title theme-arco-tabs-header-title-active"
            if "聊天详情" in self._selector or "聊天概览" in self._selector:
                return "theme-arco-tabs-header-title"
            return ""
        return None


class _TabPage(_FakePage):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.detail_selected = False
        self.clicked_selectors: list[str] = []
        self.loading_visible = False

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)
        if self.loading_visible:
            self.loading_visible = False

    def locator(self, selector: str):
        if selector == '[role="tab"]:has-text("聊天详情")':
            return _TabLocator(self, selector, visible=True)
        if selector == '[role="tab"]:has-text("聊天概览")':
            return _TabLocator(self, selector, visible=True)
        if selector in ('[data-tid="m4b_loading"]', ".theme-arco-spin", ".theme-m4b-loading"):
            return _FakeLocator(visible=self.loading_visible)
        return _FakeLocator(visible=False)


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
    detail_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
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
    detail_mock.assert_awaited_once_with(page)
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
    detail_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)
    monkeypatch.setattr(component, "_no_exportable_data", AsyncMock(return_value=True), raising=False)

    result = await component.run(page)

    export_mock.assert_not_awaited()
    detail_mock.assert_awaited_once_with(page)
    assert result.success is True
    assert result.file_path is None
    assert "no exportable" in result.message


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_fails_when_agent_detail_page_cannot_be_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    detail_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is False
    assert result.message == "failed to enter services agent detail page"
    detail_mock.assert_awaited_once_with(page)
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_tab_selected_check_rejects_visible_but_unselected_detail_tab() -> None:
    page = _TabPage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY"}))

    selected = await component._tab_looks_selected(page, ('[role="tab"]:has-text("聊天详情")',))

    assert selected is False


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_waits_for_tab_area_ready_before_clicking_detail() -> None:
    page = _TabPage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY"}))

    ready = await component._wait_tab_area_ready(page)

    assert ready is True
    assert page.clicked_selectors == []


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_enters_normal_chinese_agent_detail_tab_and_confirms_selection() -> None:
    page = _TabPage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY"}))

    ready = await component._ensure_agent_detail_ready(page)

    assert ready is True
    assert page.clicked_selectors == ['[role="tab"]:has-text("聊天详情")']
    assert page.detail_selected is True
    assert page.loading_visible is False


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_accepts_business_ready_detail_page_even_if_global_loading_still_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _TabPage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    page.detail_selected = True
    page.loading_visible = True
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY"}))

    monkeypatch.setattr(component, "_export_button_locator", AsyncMock(return_value=object()))

    ready = await component._ensure_agent_detail_ready(page)

    assert ready is True


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_treats_empty_state_as_no_exportable_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    page.visible_selectors.add("text=暂无数据")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    detail_mock = AsyncMock(return_value=True)
    date_state_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is True
    assert result.file_path is None
    assert "no exportable" in result.message
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_treats_disabled_export_button_as_no_exportable_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    page.custom_locators['button:has-text("导出数据")'] = _AttrLocator(
        attrs={
            "disabled": "",
            "class": "theme-arco-btn theme-arco-btn-disabled theme-m4b-button",
        }
    )
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    detail_mock = AsyncMock(return_value=True)
    date_state_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is True
    assert result.file_path is None
    assert "no exportable" in result.message
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_waits_for_empty_state_after_date_selection_and_completes_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    detail_mock = AsyncMock(return_value=True)
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_7_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_wait_export_readiness_state", AsyncMock(return_value="empty"))
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is True
    assert result.file_path is None
    assert "no exportable" in result.message
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_services_agent_export_waits_for_ready_state_before_running_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=MY")
    component = TiktokServicesAgentExport(_ctx({"shop_region": "MY", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    detail_mock = AsyncMock(return_value=True)
    date_state_mock = AsyncMock(return_value=True)
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/services-agent.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_ensure_agent_detail_ready", detail_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_wait_export_readiness_state", AsyncMock(return_value="ready"))
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    export_mock.assert_awaited_once()
    assert result.success is True
    assert result.file_path == "temp/services-agent.xlsx"
