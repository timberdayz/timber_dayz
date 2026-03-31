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

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)


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
    monkeypatch.setattr(component, "_run_date_picker", date_mock)
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
