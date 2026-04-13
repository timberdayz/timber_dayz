from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components import _download_helpers as download_helpers
from modules.platforms.shopee.components import products_export as products_export_module
from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_ai_assistant_export import (
    ShopeeServicesAiAssistantExport,
)
from modules.platforms.shopee.components.services_agent_export import ShopeeServicesAgentExport
from modules.platforms.shopee.components.services_export_base import ShopeeServicesExportBase


DOWNLOAD_TEXT = "\u4e0b\u8f7d"
PROCESSING_TEXT = "\u8fdb\u884c\u4e2d"


class _FakeDownload:
    def __init__(self, suggested_filename: str = "products-export.xlsx") -> None:
        self.suggested_filename = suggested_filename

    async def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"ok")


class _FakeActionLocator:
    def __init__(self, text: str) -> None:
        self._text = text
        self.click = AsyncMock()

    async def is_visible(self, *args, **kwargs) -> bool:
        return True

    async def is_enabled(self, *args, **kwargs) -> bool:
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


class _FakeNavLocator(_FakeActionLocator):
    def __init__(self, text: str, on_click=None) -> None:
        super().__init__(text)
        self._on_click = on_click
        self.click = AsyncMock(side_effect=self._click_impl)

    async def _click_impl(self, *args, **kwargs) -> None:
        if self._on_click is not None:
            self._on_click()


class _FakeLocatorSequence:
    def __init__(self, locators: list[Any]) -> None:
        self._locators = locators

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int):
        return self._locators[idx]

    @property
    def first(self):
        return self._locators[0]

    @property
    def last(self):
        return self._locators[-1]


class _FakeTextLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    async def count(self) -> int:
        return 1

    async def is_visible(self, *args, **kwargs) -> bool:
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

    def locator(self, selector: str):
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


class _DirectDownloadPage(_FakePage):
    def __init__(self) -> None:
        self.context = Mock()


class _MonthNavPage(_FakePage):
    def __init__(self, headers: list[str]) -> None:
        self._headers = headers
        self._header_idx = 0

    def locator(self, selector: str):
        if selector == "body > div":
            return _FakeLocatorSequence([self])
        if "header" in selector:
            return _FakeLocatorSequence([_FakeTextLocator(self._headers[self._header_idx])])
        return _FakeLocatorSequence([])

    def filter(self, **kwargs):
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self, timeout: int = 500) -> bool:
        return True

    async def text_content(self) -> str:
        return self._headers[self._header_idx]

    def get_by_text(self, text, exact: bool = False):
        normalized = str(text)
        if normalized in {"<", "‹"}:
            return _FakeLocatorSequence([
                _FakeNavLocator(
                    normalized,
                    on_click=lambda: None,
                )
            ])
        if normalized in {">", "›"}:
            return _FakeLocatorSequence([
                _FakeNavLocator(
                    normalized,
                    on_click=self._advance,
                )
            ])
        return _FakeLocatorSequence([])

    def _advance(self) -> None:
        if self._header_idx < len(self._headers) - 1:
            self._header_idx += 1


class _FilterablePanelLocator(_FakeTextLocator):
    def __init__(self, text: str, *, visible: bool = True) -> None:
        super().__init__(text)
        self._visible = visible

    async def is_visible(self, *args, **kwargs) -> bool:
        return self._visible


class _FilterableLocatorGroup:
    def __init__(self, locators: list[_FilterablePanelLocator]) -> None:
        self._locators = locators

    def filter(self, *, has_text: str | None = None):
        if not has_text:
            return self
        return _FilterableLocatorGroup(
            [locator for locator in self._locators if has_text in (locator._text or "")]
        )

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, idx: int):
        return self._locators[idx]


class _DatePanelDetectionPage(_FakePage):
    def __init__(self, panels: list[_FilterablePanelLocator]) -> None:
        self._panels = panels

    def locator(self, selector: str):
        if selector in (
            ".arco-trigger-popup",
            ".arco-picker-dropdown",
            ".ant-picker-dropdown",
            '[class*="picker-dropdown"]',
            '[class*="dropdown"]',
            '[class*="popup"]',
            "body > div",
            "div",
            "ul",
        ):
            return _FilterableLocatorGroup(self._panels)
        return _FilterableLocatorGroup([])


class _FutureCompletingPage(_FakePage):
    def __init__(self, waiter: asyncio.Future[_FakeDownload]) -> None:
        self._waiter = waiter
        self._wait_calls = 0

    async def wait_for_timeout(self, _ms: int) -> None:
        self._wait_calls += 1
        if self._wait_calls == 1 and not self._waiter.done():
            self._waiter.set_result(_FakeDownload("delayed-download.xlsx"))
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
async def test_products_ensure_date_ready_uses_shopee_date_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.platforms.shopee.components.date_picker as shopee_date_picker_module

    ctx = ExecutionContext(platform="shopee", account={}, config={"granularity": "weekly"})
    component = ShopeeProductsExport(ctx)
    run_picker = AsyncMock(return_value=Mock(success=True, message="ok"))
    monkeypatch.setattr(
        shopee_date_picker_module.ShopeeDatePicker,
        "run",
        run_picker,
    )
    monkeypatch.setattr(
        shopee_date_picker_module.ShopeeDatePicker,
        "_resolve_option_from_context",
        lambda self: Mock(),
    )
    monkeypatch.setattr(
        component,
        "_ensure_date_selection",
        AsyncMock(side_effect=AssertionError("products export should delegate to ShopeeDatePicker")),
        raising=False,
    )

    await component.ensure_date_ready(_FakePage())

    assert run_picker.await_count == 1


def test_direct_download_components_do_not_inherit_products_or_services_semantics() -> None:
    assert not issubclass(ShopeeAnalyticsExport, ShopeeProductsExport)
    assert not issubclass(ShopeeServicesAiAssistantExport, ShopeeServicesExportBase)


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
    top_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panels = [
        _FakePanel([_FakeRow("new-report", [_FakeActionLocator(PROCESSING_TEXT)])]),
        _FakePanel([_FakeRow("new-report", [top_download])]),
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
async def test_wait_top_report_download_button_ignores_stale_top_download_until_processing_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    component._latest_report_top_snapshot = ("stale-report", "download")
    component._latest_report_count_snapshot = 1
    stale_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panel = _FakePanel([_FakeRow("stale-report", [stale_download])])

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
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
    lower_old_download = _FakeActionLocator(DOWNLOAD_TEXT)
    top_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panels = [
        _FakePanel(
            [
                _FakeRow("top-new-report", [_FakeActionLocator(PROCESSING_TEXT)]),
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
    first_top_download = _FakeActionLocator(DOWNLOAD_TEXT)
    later_duplicate_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panels = [
        _FakePanel(
            [
                _FakeRow("parentskudetail.20260201_20260228.xlsx", [_FakeActionLocator(PROCESSING_TEXT)]),
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
    top_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panel = _FakePanel(
        [
            _FakeRow("parentskudetail.20260201_20260228.xlsx", [top_download]),
            _FakeRow("parentskudetail.20260201_20260228.xlsx", [_FakeActionLocator(DOWNLOAD_TEXT)]),
            _FakeRow("parentskudetail.20260101_20260131.xlsx", [_FakeActionLocator(DOWNLOAD_TEXT)]),
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
    top_download = _FakeActionLocator(DOWNLOAD_TEXT)
    lower_old_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panels = [
        _FakePanel(
            [
                _FakeRow("chat_20260401_20260401.xlsx", [_FakeActionLocator(PROCESSING_TEXT)]),
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
async def test_services_agent_run_uses_task_row_collection_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_agent_export as services_agent_module

    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"services_subtype": "agent", "granularity": "daily"},
    )
    component = ShopeeServicesAgentExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock(), raising=False)
    monkeypatch.setattr(
        services_agent_module.ShopeeDatePicker,
        "run",
        AsyncMock(return_value=Mock(success=True, message="ok")),
    )
    monkeypatch.setattr(
        services_agent_module.ShopeeDatePicker,
        "_resolve_option_from_context",
        lambda self: Mock(),
    )
    monkeypatch.setattr(component, "trigger_export", AsyncMock(return_value=trigger_button), raising=False)
    monkeypatch.setattr(
        component,
        "collect_download_result",
        AsyncMock(return_value="C:/tmp/services-agent.xlsx"),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_top_report_download_button",
        AsyncMock(return_value=_FakeActionLocator(DOWNLOAD_TEXT)),
        raising=False,
    )

    result = await component.run(_FakePage())

    assert component.DOWNLOAD_MODE == "task_row"
    assert result.success is True
    assert result.file_path == "C:/tmp/services-agent.xlsx"


@pytest.mark.asyncio
async def test_capture_latest_report_top_snapshot_records_top_row_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    panel = _FakePanel([_FakeRow("parentskudetail.20260201_20260228.xlsx", [_FakeActionLocator(DOWNLOAD_TEXT)])])

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


@pytest.mark.asyncio
async def test_analytics_wait_download_complete_uses_extended_download_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import analytics_export as analytics_export_module

    ctx = ExecutionContext(platform="shopee", account={}, config={"granularity": "monthly"})
    component = ShopeeAnalyticsExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()
    capture_download = AsyncMock(return_value="C:/tmp/traffic_overview.xlsx")
    monkeypatch.setattr(
        analytics_export_module.download_helpers,
        "capture_direct_download_artifact",
        capture_download,
    )

    file_path = await component.collect_download_result(_FakePage(), trigger_button)

    assert file_path == "C:/tmp/traffic_overview.xlsx"
    assert capture_download.await_args.kwargs["timeout_ms"] == 10000


@pytest.mark.asyncio
async def test_capture_direct_download_artifact_reconciles_file_from_downloads_root(
    tmp_path: Path,
) -> None:
    downloads_root = tmp_path / "downloads"
    downloads_root.mkdir()
    ctx = ExecutionContext(
        platform="shopee",
        account={"store_name": "demo-shop"},
        config={"downloads_path": str(downloads_root)},
    )
    page = _DirectDownloadPage()

    async def _click() -> None:
        (downloads_root / "traffic_overview.xlsx").write_bytes(b"ok")

    file_path = await download_helpers.capture_direct_download_artifact(
        page=page,
        click_action=_click,
        ctx=ctx,
        data_type="analytics",
        granularity="daily",
        timeout_ms=10,
        reconcile_timeout_ms=50,
        filename_hints=("traffic", "overview"),
        suggested_filename="analytics-export.xlsx",
    )

    assert file_path is not None
    assert Path(file_path).exists()
    assert "analytics" in str(file_path)


@pytest.mark.asyncio
async def test_analytics_run_returns_success_from_direct_download_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import analytics_export as analytics_export_module

    ctx = ExecutionContext(platform="shopee", account={}, config={"granularity": "daily"})
    component = ShopeeAnalyticsExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_wait_analytics_business_ready", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock(), raising=False)
    monkeypatch.setattr(
        analytics_export_module.ShopeeDatePicker,
        "run",
        AsyncMock(return_value=Mock(success=True, message="ok")),
    )
    monkeypatch.setattr(
        analytics_export_module.ShopeeDatePicker,
        "_resolve_option_from_context",
        lambda self: Mock(),
    )
    monkeypatch.setattr(component, "trigger_export", AsyncMock(return_value=trigger_button), raising=False)
    monkeypatch.setattr(
        component,
        "collect_download_result",
        AsyncMock(return_value="C:/tmp/analytics.xlsx"),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(side_effect=AssertionError("should not inspect throttled state after successful collection")),
        raising=False,
    )

    result = await component.run(_FakePage())

    assert result.success is True
    assert result.file_path == "C:/tmp/analytics.xlsx"


@pytest.mark.asyncio
async def test_analytics_ensure_page_ready_requires_business_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeAnalyticsExport(ctx)
    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_wait_analytics_business_ready", AsyncMock(return_value=False), raising=False)

    with pytest.raises(RuntimeError, match="analytics page shell loaded but business content not ready"):
        await component.ensure_page_ready(_FakePage())


@pytest.mark.asyncio
async def test_find_date_panel_for_services_does_not_require_today_realtime_anchor() -> None:
    component = ShopeeProductsExport(
        ExecutionContext(
            platform="shopee",
            account={},
            config={"data_domain": "services", "services_subtype": "agent", "granularity": "weekly"},
        )
    )
    page = _DatePanelDetectionPage(
        [
            _FilterablePanelLocator("按日 按周 按月 昨天 过去7天 过去30天"),
            _FilterablePanelLocator("页面其他内容"),
        ]
    )

    panel = await component._find_date_panel(page)

    assert panel is not None
    assert await panel.text_content() == "按日 按周 按月 昨天 过去7天 过去30天"


@pytest.mark.asyncio
async def test_shopee_date_picker_runs_custom_range_using_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage()
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={
            "data_domain": "analytics",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-30",
                "end_date": "2026-04-05",
            },
            "granularity": "weekly",
        },
    )
    picker = ShopeeDatePicker(ctx)
    monkeypatch.setattr(picker, "_current_date_summary_text", AsyncMock(return_value="旧范围"), raising=False)
    monkeypatch.setattr(picker, "_custom_date_summary_matches", lambda *args, **kwargs: False, raising=False)
    monkeypatch.setattr(picker, "_resolve_custom_target", lambda config: {
        "granularity": "weekly",
        "start_date": "2026-03-30",
        "end_date": "2026-04-05",
        "target_iso_date": "2026-03-30",
    }, raising=False)
    monkeypatch.setattr(picker, "_normalize_custom_granularity", lambda value: "weekly", raising=False)
    monkeypatch.setattr(picker, "_open_date_picker", AsyncMock(), raising=False)
    monkeypatch.setattr(picker, "_hover_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(picker, "_select_week_range_value", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(picker, "_wait_custom_date_selection_applied", AsyncMock(return_value=True), raising=False)

    result = await picker.run(page, picker._resolve_option_from_context())

    assert result.success is True
    picker._open_date_picker.assert_awaited_once()
    picker._hover_text_option.assert_awaited_once_with(page, "按周")


@pytest.mark.asyncio
async def test_services_agent_ensure_date_ready_uses_shopee_date_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_agent_export as services_agent_module

    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"services_subtype": "agent", "granularity": "weekly"},
    )
    component = ShopeeServicesAgentExport(ctx)
    run_picker = AsyncMock(return_value=Mock(success=True, message="ok"))
    monkeypatch.setattr(
        services_agent_module.ShopeeDatePicker,
        "run",
        run_picker,
    )
    monkeypatch.setattr(
        services_agent_module.ShopeeDatePicker,
        "_resolve_option_from_context",
        lambda self: Mock(),
    )
    monkeypatch.setattr(
        component,
        "_ensure_date_selection",
        AsyncMock(side_effect=AssertionError("should delegate to ShopeeDatePicker")),
        raising=False,
    )

    await component.ensure_date_ready(_FakePage())

    assert run_picker.await_count == 1


@pytest.mark.asyncio
async def test_services_ai_assistant_wait_download_complete_prefers_existing_download_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_ai_assistant_export as ai_export_module

    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"granularity": "daily", "services_subtype": "ai_assistant"},
    )
    component = ShopeeServicesAiAssistantExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()
    capture_download = AsyncMock(return_value="C:/tmp/shop_ai_assistant.xlsx")

    monkeypatch.setattr(
        ai_export_module.download_helpers,
        "capture_direct_download_artifact",
        capture_download,
    )

    file_path = await component.collect_download_result(_FakePage(), trigger_button)

    assert file_path == "C:/tmp/shop_ai_assistant.xlsx"
    assert capture_download.await_args.kwargs["subtype"] == "ai_assistant"


@pytest.mark.asyncio
async def test_wait_top_report_download_button_logs_timeout_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = Mock()
    ctx = ExecutionContext(platform="shopee", account={}, config={}, logger=logger)
    component = ShopeeProductsExport(ctx)
    component._latest_report_top_snapshot = ("baseline-report", "processing")
    component._latest_report_count_snapshot = 1
    panel = _FakePanel([_FakeRow("baseline-report", [_FakeActionLocator(PROCESSING_TEXT)])])

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=3, poll_ms=1)

    assert button is None
    assert any(
        "latest_report_download_timeout" in str(call.args[0]) and "baseline-report" in str(call.args[0])
        for call in logger.warning.call_args_list
    )


@pytest.mark.asyncio
async def test_services_ai_assistant_wait_download_complete_logs_existing_download_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_ai_assistant_export as ai_export_module

    logger = Mock()
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"granularity": "daily", "services_subtype": "ai_assistant"},
        logger=logger,
    )
    component = ShopeeServicesAiAssistantExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()

    async def _capture_direct(**kwargs):
        component.logger.info("[ShopeeExportDiag] direct_download_collection_started")
        return "C:/tmp/shop_ai_assistant.xlsx"

    monkeypatch.setattr(
        ai_export_module.download_helpers,
        "capture_direct_download_artifact",
        _capture_direct,
    )

    file_path = await component.collect_download_result(_FakePage(), trigger_button)

    assert file_path == "C:/tmp/shop_ai_assistant.xlsx"
    assert any(
        "direct_download_collection_started" in str(call.args[0])
        for call in logger.info.call_args_list
    )


@pytest.mark.asyncio
async def test_services_ai_assistant_exposes_direct_download_mode() -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"services_subtype": "ai_assistant"},
    )
    component = ShopeeServicesAiAssistantExport(ctx)

    assert component.DOWNLOAD_MODE == "direct"


@pytest.mark.asyncio
async def test_products_wait_top_report_download_button_ignores_stale_services_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    stale_services_download = _FakeActionLocator(DOWNLOAD_TEXT)
    products_download = _FakeActionLocator(DOWNLOAD_TEXT)
    panel = _FakePanel(
        [
            _FakeRow("shop_ai_assistant_20260410-20260410.xlsx", [stale_services_download]),
            _FakeRow("parentskudetail.20260301_20260331.xlsx", [products_download]),
        ]
    )

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(_FakePage(), timeout_ms=10, poll_ms=1)

    assert button is products_download


@pytest.mark.asyncio
async def test_wait_export_post_action_state_prefers_download_started_over_throttled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    completed_waiter: asyncio.Future[_FakeDownload] = asyncio.Future()
    completed_waiter.set_result(_FakeDownload("traffic_overview.xlsx"))
    component._download_waiter = completed_waiter

    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(return_value=True),
        raising=False,
    )

    state = await component._wait_export_post_action_state(_FakePage(), timeout_ms=1, poll_ms=1)

    assert state == "download_started"


@pytest.mark.asyncio
async def test_run_does_not_retry_export_after_download_started_even_if_throttled_text_lingers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)

    trigger_export = AsyncMock()
    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "ensure_date_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_trigger_export", trigger_export, raising=False)
    monkeypatch.setattr(
        component,
        "_wait_export_post_action_state",
        AsyncMock(return_value="download_started"),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(return_value=True),
        raising=False,
    )
    monkeypatch.setattr(component, "_wait_download_complete", AsyncMock(return_value="C:/tmp/traffic.xlsx"), raising=False)

    result = await component.run(_FakePage())

    assert result.success is True
    trigger_export.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_export_post_action_state_prefers_report_progress_over_throttled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    component._latest_report_top_snapshot = ("parentskudetail.old.xlsx", "download")
    component._latest_report_count_snapshot = 1
    panel = _FakePanel([_FakeRow("parentskudetail.new.xlsx", [_FakeActionLocator(PROCESSING_TEXT)])])

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=panel),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(return_value=True),
        raising=False,
    )

    state = await component._wait_export_post_action_state(_FakePage(), timeout_ms=1, poll_ms=1)

    assert state == "report_progress"


@pytest.mark.asyncio
async def test_run_does_not_retry_export_after_report_progress_even_if_throttled_text_lingers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)

    trigger_export = AsyncMock()
    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "ensure_date_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_trigger_export", trigger_export, raising=False)
    monkeypatch.setattr(
        component,
        "_wait_export_post_action_state",
        AsyncMock(return_value="report_progress"),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(return_value=True),
        raising=False,
    )
    monkeypatch.setattr(component, "_wait_download_complete", AsyncMock(return_value="C:/tmp/traffic.xlsx"), raising=False)

    result = await component.run(_FakePage())

    assert result.success is True
    trigger_export.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_top_report_download_button_exits_when_download_event_arrives_during_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    waiter: asyncio.Future[_FakeDownload] = asyncio.Future()
    component._download_waiter = waiter
    component._latest_report_top_snapshot = ("parentskudetail.old.xlsx", "download")
    component._latest_report_count_snapshot = 1
    stale_panel = _FakePanel([_FakeRow("parentskudetail.old.xlsx", [_FakeActionLocator(DOWNLOAD_TEXT)])])
    page = _FutureCompletingPage(waiter)

    monkeypatch.setattr(
        component,
        "_ensure_latest_report_panel_open",
        AsyncMock(return_value=stale_panel),
        raising=False,
    )

    button = await component._wait_top_report_download_button(page, timeout_ms=10, poll_ms=1)

    assert button is None
    assert waiter.done() is True
    assert page._wait_calls <= 2


@pytest.mark.asyncio
async def test_navigate_calendar_panel_to_month_supports_single_arrow_text_fallback() -> None:
    ctx = ExecutionContext(platform="shopee", account={}, config={})
    component = ShopeeProductsExport(ctx)
    page = _MonthNavPage(["四月2025", "五月2025", "六月2025", "三月2026"])

    result = await component._navigate_calendar_panel_to_month(page, 2026, 3)

    assert result is True


@pytest.mark.asyncio
async def test_services_ai_assistant_wait_download_complete_consumes_late_download_event_without_report_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_ai_assistant_export as ai_export_module

    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"granularity": "daily", "services_subtype": "ai_assistant"},
    )
    component = ShopeeServicesAiAssistantExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()
    capture_download = AsyncMock(return_value="C:/tmp/delayed-download.xlsx")

    monkeypatch.setattr(
        ai_export_module.download_helpers,
        "capture_direct_download_artifact",
        capture_download,
    )

    file_path = await component.collect_download_result(_FakePage(), trigger_button)

    assert file_path == "C:/tmp/delayed-download.xlsx"
    assert capture_download.await_count == 1


@pytest.mark.asyncio
async def test_services_ai_assistant_run_uses_direct_download_collection_without_report_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.platforms.shopee.components import services_ai_assistant_export as ai_export_module

    ctx = ExecutionContext(
        platform="shopee",
        account={},
        config={"granularity": "daily", "services_subtype": "ai_assistant"},
    )
    component = ShopeeServicesAiAssistantExport(ctx)
    trigger_button = Mock()
    trigger_button.click = AsyncMock()

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock(), raising=False)
    monkeypatch.setattr(
        ai_export_module.ShopeeDatePicker,
        "run",
        AsyncMock(return_value=Mock(success=True, message="ok")),
    )
    monkeypatch.setattr(
        ai_export_module.ShopeeDatePicker,
        "_resolve_option_from_context",
        lambda self: Mock(),
    )
    monkeypatch.setattr(component, "trigger_export", AsyncMock(return_value=trigger_button), raising=False)
    monkeypatch.setattr(
        component,
        "_wait_top_report_download_button",
        AsyncMock(side_effect=AssertionError("direct download flow should not wait for report-row button")),
        raising=False,
    )
    monkeypatch.setattr(
        ai_export_module.download_helpers,
        "capture_direct_download_artifact",
        AsyncMock(return_value="C:/tmp/services-ai.xlsx"),
    )

    result = await component.run(_FakePage())

    assert result.success is True
    assert result.file_path == "C:/tmp/services-ai.xlsx"
