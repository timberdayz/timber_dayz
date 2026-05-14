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


def _mark_products_ready(page: _FakePage) -> None:
    page.visible_texts.add("Product analysis")


class _DelayedProductsNavigationPage(_FakePage):
    def __init__(self, url: str, *, settle_after_waits: int = 2) -> None:
        super().__init__(url)
        self._pending_url: str | None = None
        self._settle_after_waits = settle_after_waits

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        self._pending_url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)
        if self._pending_url is not None and len(self.wait_calls) >= self._settle_after_waits:
            self.url = self._pending_url
            self._pending_url = None


class _LoadingBeforeNavigationPage(_FakePage):
    def __init__(self, url: str, *, loading_waits: int = 2) -> None:
        super().__init__(url)
        self.loading_waits = loading_waits
        self.events: list[str] = []

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.events.append(f"goto:{url}")
        await super().goto(url, wait_until=wait_until, timeout=timeout)

    async def wait_for_timeout(self, ms: int) -> None:
        self.events.append(f"wait:{ms}")
        await super().wait_for_timeout(ms)

    def locator(self, selector: str):
        if selector in ('[data-tid="m4b_loading"]', ".theme-arco-spin", ".theme-m4b-loading"):
            return _FakeLocator(visible=len(self.wait_calls) < self.loading_waits)
        return super().locator(selector)


def test_tiktok_products_export_detects_products_page_url() -> None:
    component = TiktokProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ) is True
    assert component._products_page_looks_ready(
        "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG"
    ) is False


def test_tiktok_products_export_maps_shopee_aligned_semantics_to_tiktok_date_options() -> None:
    component = TiktokProductsExport(_ctx({"granularity": "monthly"}))
    assert component._date_option_from_context() == DateOption.LAST_30_DAYS

    component = TiktokProductsExport(_ctx({"granularity": "weekly"}))
    assert component._date_option_from_context() == DateOption.LAST_7_DAYS

    component = TiktokProductsExport(_ctx({"date_preset": "today"}))
    assert component._date_option_from_context() == DateOption.TODAY_REALTIME

    component = TiktokProductsExport(_ctx({"date_preset": "yesterday"}))
    assert component._date_option_from_context() == DateOption.YESTERDAY


@pytest.mark.asyncio
async def test_tiktok_products_export_navigates_to_products_page_and_runs_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ]
    switch_mock.assert_awaited_once()
    date_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    trigger_mock.assert_awaited_once_with(page)
    collect_mock.assert_awaited_once_with(page)
    assert result.success is True
    assert result.file_path == "temp/products.xlsx"


@pytest.mark.asyncio
async def test_tiktok_products_export_deep_links_directly_from_unknown_logged_in_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/orders/list?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    ]
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_waits_for_page_to_settle_before_direct_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _LoadingBeforeNavigationPage(
        "https://seller.tiktokshopglobalselling.com/orders/list?shop_region=SG",
        loading_waits=2,
    )
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    assert result.success is True
    goto_event = "goto:https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG"
    assert goto_event in page.events
    goto_index = page.events.index(goto_event)
    assert page.events[:goto_index].count("wait:200") >= 2


@pytest.mark.asyncio
async def test_tiktok_products_export_switches_shop_context_on_products_page_after_direct_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    async def _switch_on_products_page(current_page):
        assert "/compass/product-analysis" in str(current_page.url)
        assert "/homepage" not in str(current_page.url)
        current_page.url = "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY"
        return type("R", (), {"success": True, "message": "ok"})()

    date_state_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products-my.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", _switch_on_products_page)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY"
    ]
    trigger_mock.assert_awaited_once_with(page)
    collect_mock.assert_awaited_once_with(page)
    assert result.success is True
    assert result.file_path == "temp/products-my.xlsx"


@pytest.mark.asyncio
async def test_tiktok_products_export_normalizes_region_on_products_page_without_bouncing_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    async def _switch_on_products_page(current_page):
        assert "/compass/product-analysis" in str(current_page.url)
        assert "/homepage" not in str(current_page.url)
        current_page.url = "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY"
        return type("R", (), {"success": True, "message": "ok"})()

    date_state_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products-my.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", _switch_on_products_page)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    assert result.success is True
    assert all("/homepage" not in url for url in page.goto_calls)


@pytest.mark.asyncio
async def test_tiktok_products_export_waits_until_product_analysis_navigation_settles() -> None:
    page = _DelayedProductsNavigationPage(
        "https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY",
        settle_after_waits=2,
    )
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "MY", "granularity": "monthly"}))

    current_url = await component.ensure_products_ready(page)

    assert current_url == "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY"
    assert page.goto_calls == [
        "https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=MY"
    ]


@pytest.mark.asyncio
async def test_tiktok_products_export_rejects_product_url_without_business_markers() -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    with pytest.raises(RuntimeError, match="products page is not ready"):
        await component.ensure_products_ready(page)


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
    switch_mock.assert_not_awaited()
    date_mock.assert_not_awaited()
    export_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tiktok_products_export_skips_date_picker_when_current_range_already_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "weekly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=True)
    date_mock = AsyncMock()
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    date_state_mock.assert_awaited_once_with(page, DateOption.LAST_7_DAYS)
    date_mock.assert_not_awaited()
    trigger_mock.assert_awaited_once_with(page)
    collect_mock.assert_awaited_once_with(page)
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_stops_when_date_confirmation_does_not_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=False)
    date_mock = AsyncMock(return_value=DatePickResult(success=True, message="ok", option=DateOption.LAST_30_DAYS))
    confirm_mock = AsyncMock(return_value=False)
    export_mock = AsyncMock()

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", export_mock)

    result = await component.run(page)

    confirm_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    export_mock.assert_not_awaited()
    assert result.success is False
    assert result.message == "date state not confirmed"


@pytest.mark.asyncio
async def test_tiktok_products_export_forwards_explicit_custom_range_to_date_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(
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
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
    monkeypatch.setattr(component, "_confirm_date_selection", confirm_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)

    result = await component.run(page)

    date_mock.assert_awaited_once_with(page, DateOption.LAST_30_DAYS)
    trigger_mock.assert_awaited_once_with(page)
    collect_mock.assert_awaited_once_with(page)
    assert result.success is True


@pytest.mark.asyncio
async def test_tiktok_products_export_uses_explicit_trigger_and_collect_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    _mark_products_ready(page)
    component = TiktokProductsExport(_ctx({"shop_region": "SG", "granularity": "monthly"}))

    switch_mock = AsyncMock(return_value=type("R", (), {"success": True, "message": "ok"})())
    date_state_mock = AsyncMock(return_value=True)
    trigger_mock = AsyncMock(return_value=True)
    collect_mock = AsyncMock(return_value="temp/products-delayed.xlsx")

    monkeypatch.setattr(component, "_run_shop_switch", switch_mock)
    monkeypatch.setattr(component, "_date_selection_already_satisfied", date_state_mock, raising=False)
    monkeypatch.setattr(component, "trigger_export", trigger_mock, raising=False)
    monkeypatch.setattr(component, "collect_download_result", collect_mock, raising=False)
    monkeypatch.setattr(component, "_run_export", AsyncMock(side_effect=AssertionError("should use explicit stages")), raising=False)

    result = await component.run(page)

    trigger_mock.assert_awaited_once_with(page)
    collect_mock.assert_awaited_once_with(page)
    assert result.success is True
    assert result.file_path == "temp/products-delayed.xlsx"
