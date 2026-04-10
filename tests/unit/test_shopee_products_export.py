from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components import products_export as products_export_module
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_agent_export import ShopeeServicesAgentExport


class _FakeDownload:
    def __init__(self, suggested_filename: str = "products-export.xlsx") -> None:
        self.suggested_filename = suggested_filename

    async def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"ok")


class _FakeActionLocator:
    def __init__(self, text: str) -> None:
        self._text = text
        self.click = AsyncMock()

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self) -> bool:
        return True

    async def text_content(self) -> str:
        return self._text


class _FakeActionGroup:
    def __init__(self, locators: list[_FakeActionLocator]) -> None:
        self._locators = locators

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int) -> _FakeActionLocator:
        return self._locators[idx]

    @property
    def first(self) -> _FakeActionLocator:
        return self._locators[0]


class _FakeRow:
    def __init__(self, text: str, actions: list[_FakeActionLocator]) -> None:
        self._text = text
        self._actions = actions

    async def is_visible(self) -> bool:
        return True

    async def text_content(self) -> str:
        return self._text

    def locator(self, selector: str) -> _FakeActionGroup:
        if "button" in selector or "role='button'" in selector or 'role="button"' in selector:
            return _FakeActionGroup(self._actions)
        return _FakeActionGroup([])


class _FakeRowGroup:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    async def count(self) -> int:
        return len(self._rows)

    def nth(self, idx: int) -> _FakeRow:
        return self._rows[idx]

    @property
    def first(self) -> _FakeRow:
        return self._rows[0]


class _FakePanel:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def locator(self, selector: str):
        if "button" in selector or "role='button'" in selector or 'role="button"' in selector:
            actions: list[_FakeActionLocator] = []
            for row in self._rows:
                actions.extend(row._actions)
            return _FakeActionGroup(actions)
        return _FakeRowGroup(self._rows)


class _FakePage:
    async def wait_for_timeout(self, _ms: int) -> None:
        return None


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
    panel = _FakePanel([_FakeRow("parentskudetail.20260101_20260131.xlsx", [_FakeActionLocator("\u4e0b\u8f7d")])])

    monkeypatch.setattr(
        component,
        "_wait_latest_report_panel",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=10, poll_ms=1)

    assert button is not None


@pytest.mark.asyncio
async def test_products_wait_top_report_download_button_prefers_matching_date_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    component = ShopeeProductsExport(ctx)
    old_button = _FakeActionLocator("\u4e0b\u8f7d")
    target_button = _FakeActionLocator("\u4e0b\u8f7d")
    panel = _FakePanel(
        [
            _FakeRow("parentskudetail.20260201_20260228.xlsx", [old_button]),
            _FakeRow("parentskudetail.20260101_20260131.xlsx", [target_button]),
        ]
    )

    monkeypatch.setattr(
        component,
        "_wait_latest_report_panel",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=10, poll_ms=1)

    assert button is target_button


@pytest.mark.asyncio
async def test_products_wait_top_report_download_button_waits_for_matching_processing_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    component = ShopeeProductsExport(ctx)
    old_button = _FakeActionLocator("\u4e0b\u8f7d")
    processing_button = _FakeActionLocator("\u8fdb\u884c\u4e2d")
    target_button = _FakeActionLocator("\u4e0b\u8f7d")
    panels = [
        _FakePanel(
            [
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [old_button]),
                _FakeRow("parentskudetail.20260101_20260131.xlsx", [processing_button]),
            ]
        ),
        _FakePanel(
            [
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [old_button]),
                _FakeRow("parentskudetail.20260101_20260131.xlsx", [target_button]),
            ]
        ),
    ]

    async def _next_panel(*_args, **_kwargs):
        if len(panels) > 1:
            return panels.pop(0)
        return panels[0]

    monkeypatch.setattr(
        component,
        "_wait_latest_report_panel",
        AsyncMock(side_effect=_next_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=20, poll_ms=1)

    assert button is target_button


@pytest.mark.asyncio
async def test_services_agent_wait_top_report_download_button_prefers_agent_matching_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={
            "services_subtype": "agent",
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
        },
    )
    component = ShopeeServicesAgentExport(ctx)
    old_button = _FakeActionLocator("\u4e0b\u8f7d")
    target_button = _FakeActionLocator("\u4e0b\u8f7d")
    panel = _FakePanel(
        [
            _FakeRow("chat_20260331_20260331.xlsx", [old_button]),
            _FakeRow("chat_20260401_20260401.xlsx", [target_button]),
        ]
    )

    monkeypatch.setattr(
        component,
        "_wait_latest_report_panel",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=10, poll_ms=1)

    assert button is target_button
