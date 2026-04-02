from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult
from modules.components.export.base import ExportResult
from modules.platforms.tiktok.components.products_export import TiktokProductsExport


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

    def get_by_role(self, role: str, name=None):
        key = f"{role}:{name.pattern if hasattr(name, 'pattern') else name}"
        return _FakeLocator(visible=key in self.visible_selectors)


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


def test_tiktok_products_export_detects_products_page_url() -> None:
    component = TiktokProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ) is True
    assert component._products_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG"
    ) is False


def test_tiktok_products_export_maps_supported_granularity_to_quick_date_option() -> None:
    component = TiktokProductsExport(_ctx({"granularity": "monthly"}))

    assert component._date_option_from_context() == DateOption.LAST_28_DAYS

    component = TiktokProductsExport(_ctx({"granularity": "weekly"}))
    assert component._date_option_from_context() == DateOption.LAST_7_DAYS

    component = TiktokProductsExport(_ctx({"granularity": "daily"}))
    assert component._date_option_from_context() is None


def test_tiktok_products_export_uses_current_url_shop_region_when_context_is_missing() -> None:
    component = TiktokProductsExport(
        _ctx(
            {
                "granularity": "weekly",
            }
        )
    )
    component.ctx.account["shop_region"] = ""

    assert (
        component._target_region_from_page_url(
            "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"
        )
        == "SG"
    )


@pytest.mark.asyncio
async def test_tiktok_products_export_navigates_to_products_page_and_runs_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_28_DAYS))
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ]
    switch_mock.assert_awaited_once()
    date_mock.assert_awaited_once_with(page, DateOption.LAST_28_DAYS)
    export_mock.assert_awaited_once()
    assert result.success is True
    assert result.file_path == "temp/products.xlsx"


@pytest.mark.asyncio
async def test_tiktok_products_export_returns_login_required_when_entry_state_is_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    page.visible_selectors.add("input[type='password']")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock()
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is False
    assert result.message == "login required before products export"
    assert page.goto_calls == []
    switch_mock.assert_not_awaited()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_products_export_does_not_treat_blank_login_shell_as_stable_login_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "weekly"}))

    async def _advance_page(ms: int) -> None:
        page.wait_calls.append(ms)
        if len(page.wait_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_7_DAYS))
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)
    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert len(page.wait_calls) >= 2
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_falls_back_to_current_url_region_before_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    component = TiktokProductsExport(_ctx({"granularity": "weekly"}))
    component.ctx.account["shop_region"] = ""

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_7_DAYS))
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ]
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_uses_generic_products_deep_link_when_no_region_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("about:blank")
    component = TiktokProductsExport(_ctx({"granularity": "weekly"}))
    component.ctx.account["shop_region"] = ""

    switch_mock = AsyncMock()
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_7_DAYS))
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis"
    ]
    switch_mock.assert_not_awaited()
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_returns_clear_error_when_products_deep_link_redirects_to_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("about:blank")
    page.redirect_to_login = True
    component = TiktokProductsExport(_ctx({"granularity": "weekly"}))
    component.ctx.account["shop_region"] = ""

    switch_mock = AsyncMock()
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert result.success is False
    assert result.message == "login required before products export"
    switch_mock.assert_not_awaited()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_products_export_waits_for_entry_state_to_settle_before_branching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("about:blank")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "weekly"}))

    async def _advance_page(ms: int) -> None:
        page.wait_calls.append(ms)
        if len(page.wait_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_7_DAYS))
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)
    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    assert len(page.wait_calls) >= 2
    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ]
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_skips_date_picker_when_no_supported_quick_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "daily"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock()
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    switch_mock.assert_awaited_once()
    date_mock.assert_not_awaited()
    export_mock.assert_awaited_once()
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_skips_quick_date_apply_when_current_state_already_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=True)
    date_mock = AsyncMock()
    export_mock = AsyncMock(return_value=ExportResult(success=True, message="ok", file_path="temp/products.xlsx"))

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    switch_mock.assert_awaited_once()
    date_state_mock.assert_awaited_once_with(page, DateOption.LAST_7_DAYS)
    date_mock.assert_not_awaited()
    export_mock.assert_awaited_once()
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_stops_when_date_confirmation_does_not_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_28_DAYS))
    confirm_mock = AsyncMock(return_value=False)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    date_state_mock.assert_awaited_once_with(page, DateOption.LAST_28_DAYS)
    date_mock.assert_awaited_once_with(page, DateOption.LAST_28_DAYS)
    confirm_mock.assert_awaited_once_with(page, DateOption.LAST_28_DAYS)
    export_mock.assert_not_awaited()
    assert result.success is False
    assert result.message == "date state not confirmed"


@pytest.mark.asyncio
async def test_tiktok_products_export_returns_explicit_message_for_reserved_custom_date_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    component = TiktokProductsExport(
        _ctx(
            {
                "shop_region": "SG",
                "granularity": "daily",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-07",
                },
            }
        )
    )

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_mock = AsyncMock()
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    switch_mock.assert_awaited_once()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()
    assert result.success is False
    assert result.message == "custom date is reserved for future tiktok products support"
