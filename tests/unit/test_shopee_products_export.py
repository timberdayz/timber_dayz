from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components import products_export as products_export_module
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


class _FakeDownload:
    def __init__(self, suggested_filename: str = "products-export.xlsx") -> None:
        self.suggested_filename = suggested_filename

    async def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"ok")


class _FakeActionLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    async def is_visible(self) -> bool:
        return True

    async def text_content(self) -> str:
        return self._text


class _FakeActionGroup:
    def __init__(self, texts: list[str]) -> None:
        self._locators = [_FakeActionLocator(text) for text in texts]

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int) -> _FakeActionLocator:
        return self._locators[idx]


class _FakePanel:
    def __init__(self, texts: list[str]) -> None:
        self._group = _FakeActionGroup(texts)

    def locator(self, _selector: str) -> _FakeActionGroup:
        return self._group


@pytest.mark.asyncio
async def test_products_page_ready_navigates_to_performance_url() -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={"cnsc_shop_id": "1227491331"},
        config={},
    )
    component = ShopeeProductsExport(ctx)

    page = Mock()
    page.url = ""

    async def _goto(url: str, **_: object) -> None:
        page.url = url

    page.goto = AsyncMock(side_effect=_goto)
    page.wait_for_timeout = AsyncMock()

    await component._ensure_products_page_ready(page)

    assert (
        page.goto.await_args.args[0]
        == "https://seller.shopee.cn/datacenter/product/performance?cnsc_shop_id=1227491331"
    )


@pytest.mark.asyncio
async def test_wait_download_complete_clicks_latest_report_download_button(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={"granularity": "weekly"})
    component = ShopeeProductsExport(ctx)

    latest_report_download_button = Mock()
    latest_report_download_button.click = AsyncMock()

    async def _return_download() -> _FakeDownload:
        return _FakeDownload()

    component._download_waiter = asyncio.create_task(_return_download())

    monkeypatch.setattr(
        component,
        "_wait_top_report_download_button",
        AsyncMock(return_value=latest_report_download_button),
        raising=False,
    )
    monkeypatch.setattr(
        products_export_module,
        "build_standard_output_root",
        lambda *args, **kwargs: tmp_path,
    )

    file_path = await component._wait_download_complete(Mock())

    latest_report_download_button.click.assert_awaited_once()
    assert file_path == str(tmp_path / "products-export.xlsx")


@pytest.mark.asyncio
async def test_wait_top_report_download_button_recognizes_download_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    panel = _FakePanel(["下载"])

    monkeypatch.setattr(
        component,
        "_wait_latest_report_panel",
        AsyncMock(return_value=panel),
        raising=False,
    )

    class _Page:
        async def wait_for_timeout(self, _ms: int) -> None:
            return None

    button = await component._wait_top_report_download_button(_Page(), timeout_ms=10, poll_ms=1)

    assert button is not None
