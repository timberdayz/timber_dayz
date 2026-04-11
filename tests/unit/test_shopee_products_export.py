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


class _FakeTextLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    async def is_visible(self) -> bool:
        return True

    async def text_content(self) -> str:
        return self._text


class _FakeTextGroup:
    def __init__(self, texts: list[str]) -> None:
        self._locators = [_FakeTextLocator(text) for text in texts]

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int) -> _FakeTextLocator:
        return self._locators[idx]

    @property
    def first(self) -> _FakeTextLocator:
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
        if "status" in selector:
            return _FakeTextGroup([action._text for action in self._actions if action._text])
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
async def test_wait_top_report_download_button_returns_top_download_after_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    panels = [
        _FakePanel([_FakeRow("new-report", [_FakeActionLocator("进行中")])]),
        _FakePanel([_FakeRow("new-report", [_FakeActionLocator("下载")])]),
    ]

    async def _next_panel(*_args, **_kwargs):
        if len(panels) > 1:
            return panels.pop(0)
        return panels[0]

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(side_effect=_next_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=20, poll_ms=1)

    assert button is panels[0]._rows[0]._actions[0]


@pytest.mark.asyncio
async def test_wait_top_report_download_button_ignores_stale_top_download_until_processing_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    component._latest_report_top_snapshot = ("stale-report", "download")
    component._latest_report_count_snapshot = 1
    stale_download = _FakeActionLocator("下载")
    panels = [_FakePanel([_FakeRow("stale-report", [stale_download])])]

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panels[0]),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=3, poll_ms=1)

    assert button is None


@pytest.mark.asyncio
async def test_products_wait_top_report_download_button_prefers_top_slot_over_lower_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    lower_old_download = _FakeActionLocator("下载")
    top_processing = _FakeActionLocator("进行中")
    top_download = _FakeActionLocator("下载")
    panels = [
        _FakePanel(
            [
                _FakeRow("top-new-report", [top_processing]),
                _FakeRow("old-report", [lower_old_download]),
            ]
        ),
        _FakePanel(
            [
                _FakeRow("top-new-report", [top_download]),
                _FakeRow("old-report", [lower_old_download]),
            ]
        ),
    ]

    async def _next_panel(*_args, **_kwargs):
        if len(panels) > 1:
            return panels.pop(0)
        return panels[0]

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(side_effect=_next_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=20, poll_ms=1)

    assert button is top_download


@pytest.mark.asyncio
async def test_products_wait_top_report_download_button_prefers_first_duplicate_candidate_after_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    first_top_processing = _FakeActionLocator("进行中")
    first_top_download = _FakeActionLocator("下载")
    later_duplicate_download = _FakeActionLocator("下载")
    panels = [
        _FakePanel(
            [
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [first_top_processing]),
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [later_duplicate_download]),
            ]
        ),
        _FakePanel(
            [
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [first_top_download]),
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [later_duplicate_download]),
            ]
        ),
    ]

    async def _next_panel(*_args, **_kwargs):
        if len(panels) > 1:
            return panels.pop(0)
        return panels[0]

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(side_effect=_next_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=20, poll_ms=1)

    assert button is first_top_download


@pytest.mark.asyncio
async def test_wait_top_report_download_button_accepts_top_download_when_count_increases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    component._latest_report_top_snapshot = ("parentskudetail.20260201_20260228.xlsx", "download")
    component._latest_report_count_snapshot = 2
    top_download = _FakeActionLocator("涓嬭浇")
    panel = _FakePanel(
        [
            _FakeRow("parentskudetail.20260201_20260228.xlsx", [top_download]),
            _FakeRow("parentskudetail.20260201_20260228.xlsx", [_FakeActionLocator("涓嬭浇")]),
            _FakeRow("parentskudetail.20260101_20260131.xlsx", [_FakeActionLocator("涓嬭浇")]),
        ]
    )

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=10, poll_ms=1)

    assert button is top_download


@pytest.mark.asyncio
async def test_services_agent_wait_top_report_download_button_uses_same_top_slot_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"services_subtype": "agent"},
    )
    component = ShopeeServicesAgentExport(ctx)
    top_processing = _FakeActionLocator("进行中")
    top_download = _FakeActionLocator("下载")
    lower_old_download = _FakeActionLocator("下载")
    panels = [
        _FakePanel(
            [
                _FakeRow("chat_20260401_20260401.xlsx", [top_processing]),
                _FakeRow("chat_20260401_20260401.xlsx", [lower_old_download]),
            ]
        ),
        _FakePanel(
            [
                _FakeRow("chat_20260401_20260401.xlsx", [top_download]),
                _FakeRow("chat_20260401_20260401.xlsx", [lower_old_download]),
            ]
        ),
    ]

    async def _next_panel(*_args, **_kwargs):
        if len(panels) > 1:
            return panels.pop(0)
        return panels[0]

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(side_effect=_next_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=20, poll_ms=1)

    assert button is top_download


@pytest.mark.asyncio
async def test_capture_latest_report_top_snapshot_records_top_row_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    panel = _FakePanel([_FakeRow("parentskudetail.20260201_20260228.xlsx", [_FakeActionLocator("下载")])])

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
        raising=False,
    )

    await component._capture_latest_report_top_snapshot(_FakePage())

    assert component._latest_report_top_snapshot == (
        "parentskudetail.20260201_20260228.xlsx",
        "download",
    )
