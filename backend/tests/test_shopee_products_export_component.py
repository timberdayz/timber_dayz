from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportMode
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="shopee",
        account={
            "username": "user",
            "store_name": "shop-a",
            "login_url": "https://seller.shopee.cn/account/signin?next=%2F",
        },
        logger=None,
        config=config or {
            "shop_name": "shop-a",
            "granularity": "daily",
        },
    )


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.wait_calls: list[int] = []

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def locator(self, selector: str):
        return _FakeLocator(visible=False, count=0)


class _FakeDownload:
    def __init__(self, suggested_filename: str = "products-export.xlsx", *, payload: bytes | None = None, no_op: bool = False) -> None:
        self.suggested_filename = suggested_filename
        self._payload = payload
        self._no_op = no_op

    async def save_as(self, path: str) -> None:
        if self._no_op:
            return
        if self._payload is None:
            return
        with open(path, "wb") as f:
            f.write(self._payload)


class _FakeLocator:
    def __init__(self, text: str | None = None, *, visible: bool = True, count: int = 1) -> None:
        self._text = text
        self._visible = visible
        self._count = count
        self.clicked = False
        self.hovered = False

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return self._count

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def text_content(self) -> str | None:
        return self._text

    async def click(self, timeout: int | None = None) -> None:
        self.clicked = True

    async def hover(self, timeout: int | None = None) -> None:
        self.hovered = True


class _FakeTextMatch:
    def __init__(self, first: _FakeLocator, last: _FakeLocator) -> None:
        self.first = first
        self.last = last


class _FakeLocatorGroup:
    def __init__(self, locators: list[_FakeLocator]) -> None:
        self._locators = locators

    @property
    def first(self):
        return self._locators[0] if self._locators else _FakeLocator(visible=False, count=0)

    @property
    def last(self):
        return self._locators[-1] if self._locators else _FakeLocator(visible=False, count=0)

    async def count(self) -> int:
        return len(self._locators)

    def nth(self, index: int):
        if 0 <= index < len(self._locators):
            return self._locators[index]
        return _FakeLocator(visible=False, count=0)


class _DateFallbackPage(_FakePage):
    def __init__(self, url: str, text_locators: dict[str, _FakeLocator]) -> None:
        super().__init__(url)
        self.text_locators = text_locators

    def locator(self, selector: str):
        return _FakeLocator(visible=False, count=0)

    def get_by_text(self, text: str, exact: bool = False):
        if isinstance(text, re.Pattern):
            for key, locator in self.text_locators.items():
                if text.search(key):
                    return locator
            return _FakeLocator(visible=False, count=0)
        return self.text_locators.get(text, _FakeLocator(visible=False, count=0))


class _DateMenuPage(_FakePage):
    def __init__(self, url: str, text_matches: dict[str, _FakeTextMatch]) -> None:
        super().__init__(url)
        self.text_matches = text_matches

    def locator(self, selector: str):
        return _FakeLocator(visible=False, count=0)

    def get_by_text(self, text: str, exact: bool = False):
        if isinstance(text, re.Pattern):
            for key, match in self.text_matches.items():
                if text.search(key):
                    return match
            return _FakeTextMatch(_FakeLocator(visible=False, count=0), _FakeLocator(visible=False, count=0))
        return self.text_matches.get(
            text,
            _FakeTextMatch(_FakeLocator(visible=False, count=0), _FakeLocator(visible=False, count=0)),
        )


class _FakePanel:
    def __init__(self, text_matches: dict[str, _FakeTextMatch]) -> None:
        self.text_matches = text_matches

    def get_by_text(self, text: str, exact: bool = False):
        if isinstance(text, re.Pattern):
            for key, match in self.text_matches.items():
                if text.search(key):
                    return match
            return _FakeTextMatch(_FakeLocator(visible=False, count=0), _FakeLocator(visible=False, count=0))
        return self.text_matches.get(
            text,
            _FakeTextMatch(_FakeLocator(visible=False, count=0), _FakeLocator(visible=False, count=0)),
        )


class _NavPanel(_FakePanel):
    def __init__(self, text_matches: dict[str, object], selector_locators: dict[str, _FakeLocator] | None = None) -> None:
        super().__init__({})
        self.text_matches = text_matches
        self.selector_locators = selector_locators or {}

    def locator(self, selector: str):
        return self.selector_locators.get(selector, _FakeLocator(visible=False, count=0))


def test_shopee_products_export_accepts_products_overview_url() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1"
    ) is True


def test_shopee_products_export_rejects_non_products_url() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1"
    ) is False


def test_shopee_products_export_detects_throttled_text() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._is_export_throttled("点击过快，请稍后再试") is True
    assert component._is_export_throttled("导出成功") is False


def test_shopee_products_export_shop_label_detection_requires_current_value() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._shop_name_looks_selected("新加坡 / chenewei666.sg", "chenewei666.sg") is True
    assert component._shop_name_looks_selected("所有店铺 chenewei666.sg zewei_toys.sg", "chenewei666.sg") is False


def test_shopee_products_export_shop_label_detection_respects_region_context() -> None:
    component = ShopeeProductsExport(_ctx({"shop_name": "chenewei666.sg", "shop_region": "SG"}))

    assert component._shop_name_looks_selected("新加坡 / chenewei666.sg", "chenewei666.sg", "SG") is True
    assert component._shop_name_looks_selected("巴西 / chenewei666.sg", "chenewei666.sg", "SG") is False


def test_shopee_products_export_maps_granularity_to_summary_preset_labels() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._target_date_label({"granularity": "daily"}) == "昨天"
    assert component._target_date_label({"granularity": "weekly"}) == "过去7天"
    assert component._target_date_label({"granularity": "monthly"}) == "过去30天"


def test_shopee_products_export_resolve_custom_target_uses_start_date_for_daily() -> None:
    component = ShopeeProductsExport(
        _ctx(
            {
                "granularity": "daily",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-03-09",
                    "end_date": "2026-03-15",
                },
            }
        )
    )

    target = component._resolve_custom_target(component.ctx.config or {})

    assert target["granularity"] == "daily"
    assert target["target_iso_date"] == "2026-03-09"
    assert target["target_year"] == 2026
    assert target["target_month"] == 3
    assert target["target_day"] == 9


def test_shopee_products_export_resolve_custom_target_uses_start_date_for_weekly() -> None:
    component = ShopeeProductsExport(
        _ctx(
            {
                "granularity": "weekly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2025-11-03",
                    "end_date": "2025-11-09",
                },
            }
        )
    )

    target = component._resolve_custom_target(component.ctx.config or {})

    assert target["granularity"] == "weekly"
    assert target["target_iso_date"] == "2025-11-03"
    assert target["target_year"] == 2025
    assert target["target_month"] == 11
    assert target["target_day"] == 3


def test_shopee_products_export_resolve_custom_target_uses_start_date_for_monthly() -> None:
    component = ShopeeProductsExport(
        _ctx(
            {
                "granularity": "monthly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2025-11-01",
                    "end_date": "2025-11-30",
                },
            }
        )
    )

    target = component._resolve_custom_target(component.ctx.config or {})

    assert target["granularity"] == "monthly"
    assert target["target_iso_date"] == "2025-11-01"
    assert target["target_year"] == 2025
    assert target["target_month"] == 11
    assert target["target_day"] == 1
    assert target["target_month_label_zh"] == "十一月"


def test_shopee_products_export_month_leaf_labels_use_chinese_names_only() -> None:
    component = ShopeeProductsExport(_ctx())

    labels = component._month_leaf_labels("2026-02-01")

    assert labels == ("\u4e8c\u6708",)


@pytest.mark.asyncio
async def test_shopee_products_export_current_date_label_reads_trigger_summary_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())
    component.sel = SimpleNamespace(
        date_picker_triggers=("summary",),
        preset_labels={
            "today_realtime": "Today realtime",
            "yesterday": "Yesterday",
            "last_7_days": "Near 7 days",
            "last_30_days": "Near 30 days",
        },
        granularity_labels={
            "daily": "By Day",
            "weekly": "By Week",
            "monthly": "By Month",
        },
    )

    monkeypatch.setattr(
        component,
        "_find_date_picker_trigger",
        AsyncMock(return_value=_FakeLocator("Stats Time Today realtime Today 14:00 (GMT+08)")),
        raising=False,
    )
    monkeypatch.setattr(component, "_visible_text", AsyncMock(return_value=False))

    current = await component._current_date_label(page)

    assert current == "Today realtime"


@pytest.mark.asyncio
async def test_shopee_products_export_current_date_label_recognizes_range_summary_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(
        component,
        "_find_date_picker_trigger",
        AsyncMock(return_value=_FakeLocator("统计时间 过去7 天 24-03-2026 - 30-03-2026 (GMT+08)")),
        raising=False,
    )
    monkeypatch.setattr(component, "_visible_text", AsyncMock(return_value=False))

    current = await component._current_date_label(page)

    assert current == "过去7天"


@pytest.mark.asyncio
async def test_shopee_products_export_current_date_label_uses_visible_match_not_hidden_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {"过去30天": _FakeTextMatch(_FakeLocator("过去30天", visible=False), _FakeLocator("过去30天", visible=True))},
    )
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_picker_trigger", AsyncMock(return_value=None), raising=False)

    current = await component._current_date_label(page)

    assert current == "过去30天"


@pytest.mark.asyncio
async def test_shopee_products_export_open_date_picker_falls_back_to_summary_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = _FakeLocator("\u7edf\u8ba1\u65f6\u95f4 \u4eca\u65e5\u5b9e\u65f6")
    page = _DateFallbackPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {"\u7edf\u8ba1\u65f6\u95f4": trigger},
    )
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(page, "wait_for_timeout", AsyncMock())

    await component._open_date_picker(page)

    assert trigger.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_click_text_option_prefers_date_menu_entry_over_summary() -> None:
    summary = _FakeLocator("过去7天", visible=True)
    menu_item = _FakeLocator("过去7天", visible=True)
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {"过去7天": _FakeTextMatch(summary, menu_item)},
    )
    component = ShopeeProductsExport(_ctx())

    clicked = await component._click_text_option(page, "过去7天")

    assert clicked is True
    assert summary.clicked is False
    assert menu_item.hovered is True
    assert menu_item.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_find_date_option_locator_prefers_panel_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {"过去7天": _FakeTextMatch(_FakeLocator("过去7天", visible=True), _FakeLocator("过去7天", visible=True))},
    )
    panel_item = _FakeLocator("过去7天", visible=True)
    panel = _FakePanel({"过去7天": _FakeTextMatch(_FakeLocator("过去7天", visible=True), panel_item)})
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)

    locator = await component._find_date_option_locator(page, "过去7天")

    assert locator is panel_item


@pytest.mark.asyncio
async def test_shopee_products_export_find_date_option_locator_matches_panel_text_with_spacing_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel_item = _FakeLocator("过去7 天", visible=True)
    panel = _FakePanel({"过去7 天": _FakeTextMatch(_FakeLocator("过去7 天", visible=True), panel_item)})
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {},
    )
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)

    locator = await component._find_date_option_locator(page, "过去7天")

    assert locator is panel_item


@pytest.mark.asyncio
async def test_shopee_products_export_waits_for_shop_selection_to_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx({"shop_name": "chenewei666.sg", "shop_region": "SG"}))

    monkeypatch.setattr(
        component,
        "_visible_text_content",
        AsyncMock(side_effect=["所有店铺 chenewei666.sg zewei_toys.sg", "新加坡 / chenewei666.sg"]),
    )

    applied = await component._wait_shop_selection_applied(page, "chenewei666.sg", "SG", timeout_ms=1000, poll_ms=200)

    assert applied is True
    assert page.wait_calls == [200]


@pytest.mark.asyncio
async def test_shopee_products_export_skips_date_picker_when_target_already_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx({"shop_name": "shop-a", "granularity": "daily"}))

    monkeypatch.setattr(component, "_current_date_label", AsyncMock(return_value="昨天"))
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock())

    await component._ensure_date_selection(page)

    component._open_date_picker.assert_not_awaited()
    component._click_text_option.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_products_export_uses_single_day_selection_for_yesterday_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(
        _ctx(
            {
                "shop_name": "shop-a",
                "granularity": "daily",
                "date_preset": "yesterday",
                "end_date": "2026-03-30",
            }
        )
    )

    monkeypatch.setattr(component, "_current_date_label", AsyncMock(return_value="今日实时"))
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_hover_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_single_day_value", AsyncMock(), raising=False)
    monkeypatch.setattr(component, "_wait_date_selection_applied", AsyncMock(return_value=True), raising=False)

    await component._ensure_date_selection(page)

    component._open_date_picker.assert_awaited_once()
    component._hover_text_option.assert_awaited_once_with(page, "按日")
    component._select_single_day_value.assert_awaited_once_with(page, "2026-03-30")


@pytest.mark.asyncio
async def test_shopee_products_export_ensure_date_selection_raises_when_summary_does_not_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(
        _ctx({"shop_name": "shop-a", "date_preset": "last_7_days", "granularity": "weekly"})
    )

    monkeypatch.setattr(
        component,
        "_current_date_label",
        AsyncMock(return_value="今日实时"),
    )
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_wait_date_selection_applied", AsyncMock(return_value=False), raising=False)

    with pytest.raises(RuntimeError, match="date selection"):
        await component._ensure_date_selection(page)


@pytest.mark.asyncio
async def test_shopee_products_export_ensure_date_selection_raises_when_quick_option_not_clicked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(
        _ctx({"shop_name": "shop-a", "date_preset": "last_7_days", "granularity": "weekly"})
    )

    monkeypatch.setattr(component, "_current_date_label", AsyncMock(return_value="今日实时"))
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock(return_value=False))

    with pytest.raises(RuntimeError, match="date option"):
        await component._ensure_date_selection(page)


@pytest.mark.asyncio
async def test_shopee_products_export_custom_weekly_uses_week_mode_instead_of_quick_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(
        _ctx(
            {
                "shop_name": "shop-a",
                "granularity": "weekly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-03-09",
                    "end_date": "2026-03-15",
                },
                "start_date": "2026-03-09",
                "end_date": "2026-03-15",
            }
        )
    )

    monkeypatch.setattr(component, "_current_date_label", AsyncMock(return_value="今日实时"))
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_hover_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_week_range_value", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_wait_custom_date_selection_applied", AsyncMock(return_value=True), raising=False)

    await component._ensure_date_selection(page)

    component._hover_text_option.assert_awaited_once_with(page, "按周")
    component._select_week_range_value.assert_awaited_once_with(page, "2026-03-09", "2026-03-15")
    component._click_text_option.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_products_export_custom_monthly_uses_month_mode_instead_of_quick_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(
        _ctx(
            {
                "shop_name": "shop-a",
                "granularity": "monthly",
                "time_selection": {
                    "mode": "custom",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-31",
                },
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            }
        )
    )

    monkeypatch.setattr(component, "_current_date_label", AsyncMock(return_value="今日实时"))
    monkeypatch.setattr(component, "_open_date_picker", AsyncMock())
    monkeypatch.setattr(component, "_click_text_option", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_hover_text_option", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_month_value", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_wait_custom_date_selection_applied", AsyncMock(return_value=True), raising=False)

    await component._ensure_date_selection(page)

    component._hover_text_option.assert_awaited_once_with(page, "按月")
    component._select_month_value.assert_awaited_once_with(page, "2026-03-01")
    component._click_text_option.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_products_export_select_month_value_navigates_year_before_clicking_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())
    month_leaf = _FakeLocator("2月", visible=True)

    monkeypatch.setattr(component, "_navigate_month_panel_to_year", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_find_month_leaf_locator", AsyncMock(return_value=month_leaf), raising=False)

    selected = await component._select_month_value(page, "2026-02-01")

    assert selected is True
    component._navigate_month_panel_to_year.assert_awaited_once_with(page, 2026)
    assert month_leaf.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_select_month_value_does_not_misclick_december_for_february(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    december = _FakeLocator("12月", visible=True)
    february = _FakeLocator("2月", visible=True)
    panel = _FakePanel(
        {
            "12月": _FakeTextMatch(_FakeLocator("12月", visible=True), december),
            "2月": _FakeTextMatch(_FakeLocator("2月", visible=True), february),
        }
    )
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)
    monkeypatch.setattr(component, "_navigate_month_panel_to_year", AsyncMock(return_value=True), raising=False)

    selected = await component._select_month_value(page, "2026-02-01")

    assert selected is True
    assert december.clicked is False
    assert february.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_find_month_leaf_locator_falls_back_when_panel_scope_misses_month_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {"\u4e8c\u6708": _FakeTextMatch(_FakeLocator("\u4e8c\u6708", visible=True), _FakeLocator("\u4e8c\u6708", visible=True))},
    )
    panel = _FakePanel({})
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)

    locator = await component._find_month_leaf_locator(page, "2026-02-01")

    assert locator is not None
    assert await locator.is_visible() is True


@pytest.mark.asyncio
async def test_shopee_products_export_find_month_leaf_locator_uses_month_specific_pattern_without_matching_december(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _DateMenuPage(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1",
        {
            "\u5341\u4e8c\u6708": _FakeTextMatch(
                _FakeLocator("\u5341\u4e8c\u6708", visible=True),
                _FakeLocator("\u5341\u4e8c\u6708", visible=True),
            ),
            "\u4e8c\u6708": _FakeTextMatch(
                _FakeLocator("\u4e8c\u6708", visible=True),
                _FakeLocator("\u4e8c\u6708", visible=True),
            ),
        },
    )
    component = ShopeeProductsExport(_ctx())
    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=None), raising=False)

    locator = await component._find_month_leaf_locator(page, "2026-02-01")

    assert locator is not None
    assert await locator.text_content() == "\u4e8c\u6708"


@pytest.mark.asyncio
async def test_shopee_products_export_select_week_range_value_navigates_calendar_month_before_clicking_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_navigate_calendar_panel_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_calendar_day", AsyncMock(return_value=True), raising=False)

    selected = await component._select_week_range_value(page, "2026-03-09", "2026-03-15")

    assert selected is True
    component._navigate_calendar_panel_to_month.assert_awaited_once_with(page, 2026, 3)
    component._select_calendar_day.assert_awaited_once_with(page, 15)


@pytest.mark.asyncio
async def test_shopee_products_export_succeeds_when_download_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        component,
        "_wait_export_post_action_state",
        AsyncMock(return_value="download_started"),
        raising=False,
    )
    monkeypatch.setattr(
        component,
        "_wait_download_complete",
        AsyncMock(return_value="F:/tmp/products.xlsx"),
    )

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is True
    assert result.file_path == "F:/tmp/products.xlsx"
    component._wait_export_post_action_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_shopee_products_export_wait_download_complete_rejects_stale_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())
    stale_file = tmp_path / "products-export.xlsx"
    stale_file.write_bytes(b"old-data")

    future = asyncio.get_running_loop().create_future()
    future.set_result(_FakeDownload(no_op=True))
    component._download_waiter = future

    monkeypatch.setattr(
        "modules.platforms.shopee.components.products_export.build_standard_output_root",
        lambda ctx, data_type, granularity: tmp_path,
    )

    result = await component._wait_download_complete(page)

    assert result is None


@pytest.mark.asyncio
async def test_shopee_products_export_wait_download_complete_rejects_empty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    future = asyncio.get_running_loop().create_future()
    future.set_result(_FakeDownload(payload=b""))
    component._download_waiter = future

    monkeypatch.setattr(
        "modules.platforms.shopee.components.products_export.build_standard_output_root",
        lambda ctx, data_type, granularity: tmp_path,
    )

    result = await component._wait_download_complete(page)

    assert result is None


@pytest.mark.asyncio
async def test_shopee_products_export_wait_export_post_action_state_returns_unknown_when_dom_stays_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=False))
    component._download_waiter = None

    state = await component._wait_export_post_action_state(page, timeout_ms=1000, poll_ms=500)

    assert state == "unknown"
    assert page.wait_calls == [500, 500, 500]


@pytest.mark.asyncio
async def test_shopee_products_export_retries_after_throttled_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(
        component,
        "_wait_export_post_action_state",
        AsyncMock(side_effect=["throttled", "download_started"]),
    )
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(component, "_wait_export_retry_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(
        component,
        "_wait_download_complete",
        AsyncMock(return_value="F:/tmp/products.xlsx"),
    )

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is True
    assert result.file_path == "F:/tmp/products.xlsx"
    assert component._trigger_export.await_count == 2


@pytest.mark.asyncio
async def test_shopee_products_export_rechecks_post_action_state_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(
        component,
        "_wait_export_post_action_state",
        AsyncMock(side_effect=["throttled", "download_started"]),
    )
    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_wait_export_retry_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(
        component,
        "_wait_download_complete",
        AsyncMock(return_value="F:/tmp/products.xlsx"),
    )

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is True
    assert component._wait_export_post_action_state.await_count == 2


@pytest.mark.asyncio
async def test_shopee_products_export_fails_when_throttled_and_never_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_wait_export_retry_ready", AsyncMock(return_value=False))

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is False
    assert "throttled" in result.message


@pytest.mark.asyncio
async def test_shopee_products_export_select_month_value_navigates_year_before_clicking_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())
    month_leaf = _FakeLocator("\u4e8c\u6708", visible=True)

    monkeypatch.setattr(component, "_navigate_month_panel_to_year", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_find_month_leaf_locator", AsyncMock(return_value=month_leaf), raising=False)

    selected = await component._select_month_value(page, "2026-02-01")

    assert selected is True
    component._navigate_month_panel_to_year.assert_awaited_once_with(page, 2026)
    assert month_leaf.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_select_month_value_does_not_misclick_december_for_february(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    december = _FakeLocator("\u5341\u4e8c\u6708", visible=True)
    february = _FakeLocator("\u4e8c\u6708", visible=True)
    panel = _FakePanel(
        {
            "\u5341\u4e8c\u6708": _FakeTextMatch(_FakeLocator("\u5341\u4e8c\u6708", visible=True), december),
            "\u4e8c\u6708": _FakeTextMatch(_FakeLocator("\u4e8c\u6708", visible=True), february),
        }
    )
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)
    monkeypatch.setattr(component, "_navigate_month_panel_to_year", AsyncMock(return_value=True), raising=False)

    selected = await component._select_month_value(page, "2026-02-01")

    assert selected is True
    assert december.clicked is False
    assert february.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_select_week_range_value_navigates_calendar_month_before_clicking_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_navigate_calendar_panel_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_calendar_day", AsyncMock(return_value=True), raising=False)

    selected = await component._select_week_range_value(page, "2026-03-09", "2026-03-15")

    assert selected is True
    component._navigate_calendar_panel_to_month.assert_awaited_once_with(page, 2026, 3)
    component._select_calendar_day.assert_awaited_once_with(page, 9)


@pytest.mark.asyncio
async def test_shopee_products_export_select_single_day_value_navigates_calendar_month_before_clicking_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_navigate_calendar_panel_to_month", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_select_calendar_day", AsyncMock(return_value=True), raising=False)

    selected = await component._select_single_day_value(page, "2026-03-09")

    assert selected is True
    component._navigate_calendar_panel_to_month.assert_awaited_once_with(page, 2026, 3)
    component._select_calendar_day.assert_awaited_once_with(page, 9)


@pytest.mark.asyncio
async def test_shopee_products_export_navigate_calendar_month_uses_month_arrows_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(
        component,
        "_current_popup_header_text",
        AsyncMock(side_effect=["\u4e09\u67082026", "\u4e8c\u67082026"]),
        raising=False,
    )
    monkeypatch.setattr(component, "_click_popup_month_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_click_popup_year_nav_button", AsyncMock(return_value=True), raising=False)

    reached = await component._navigate_calendar_panel_to_month(page, 2026, 2)

    assert reached is True
    component._click_popup_month_nav_button.assert_awaited_once_with(page, "prev")
    component._click_popup_year_nav_button.assert_not_awaited()


def test_shopee_products_export_parse_calendar_header_month_year_zh() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._parse_calendar_header_month_year_zh("\u56db\u67082026") == (2026, 4)
    assert component._parse_calendar_header_month_year_zh("\u5341\u4e8c\u67082025") == (2025, 12)
    assert component._parse_calendar_header_month_year_zh("2026.04") is None


@pytest.mark.asyncio
async def test_shopee_products_export_navigate_calendar_month_waits_for_header_change_between_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(
        component,
        "_current_popup_header_text",
        AsyncMock(side_effect=["\u56db\u67082026", "\u4e09\u67082026", "\u4e8c\u67082026"]),
        raising=False,
    )
    monkeypatch.setattr(component, "_click_popup_month_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(
        component,
        "_wait_calendar_header_changed",
        AsyncMock(side_effect=["\u4e09\u67082026", "\u4e8c\u67082026"]),
        raising=False,
    )

    reached = await component._navigate_calendar_panel_to_month(page, 2026, 2)

    assert reached is True
    assert component._click_popup_month_nav_button.await_count == 2
    component._wait_calendar_header_changed.assert_any_await(page, "\u56db\u67082026")
    component._wait_calendar_header_changed.assert_any_await(page, "\u4e09\u67082026")


@pytest.mark.asyncio
async def test_shopee_products_export_navigate_month_panel_uses_year_arrows_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(
        component,
        "_current_popup_header_text",
        AsyncMock(side_effect=["2026", "2025"]),
        raising=False,
    )
    monkeypatch.setattr(component, "_click_popup_year_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_click_popup_month_nav_button", AsyncMock(return_value=True), raising=False)

    reached = await component._navigate_month_panel_to_year(page, 2025)

    assert reached is True
    component._click_popup_year_nav_button.assert_awaited_once_with(page, "prev")
    component._click_popup_month_nav_button.assert_not_awaited()


def test_shopee_products_export_parse_month_panel_year() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._parse_month_panel_year("2025") == 2025
    assert component._parse_month_panel_year(" 2026 ") == 2026
    assert component._parse_month_panel_year("\u56db\u67082026") is None


@pytest.mark.asyncio
async def test_shopee_products_export_navigate_month_panel_waits_for_year_change_between_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(
        component,
        "_current_popup_header_text",
        AsyncMock(side_effect=["2027", "2026", "2025"]),
        raising=False,
    )
    monkeypatch.setattr(component, "_click_popup_year_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(component, "_click_popup_month_nav_button", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(
        component,
        "_wait_calendar_header_changed",
        AsyncMock(side_effect=["2026", "2025"]),
        raising=False,
    )

    reached = await component._navigate_month_panel_to_year(page, 2025)

    assert reached is True
    assert component._click_popup_year_nav_button.await_count == 2
    component._wait_calendar_header_changed.assert_any_await(page, "2027")
    component._wait_calendar_header_changed.assert_any_await(page, "2026")
    component._click_popup_month_nav_button.assert_not_awaited()


@pytest.mark.asyncio
async def test_shopee_products_export_click_popup_year_nav_button_falls_back_to_text_arrows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prev_text = _FakeLocator("<<", visible=True)
    panel = _NavPanel(
        {
            "<<": _FakeLocatorGroup([prev_text]),
        }
    )
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)

    clicked = await component._click_popup_year_nav_button(page, "prev")

    assert clicked is True
    assert prev_text.clicked is True


@pytest.mark.asyncio
async def test_shopee_products_export_find_month_leaf_locator_scans_all_visible_matches_not_only_first_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden_first = _FakeLocator("\u4e8c\u6708", visible=False)
    target_middle = _FakeLocator("\u4e8c\u6708", visible=True)
    hidden_last = _FakeLocator("\u4e8c\u6708", visible=False)
    panel = _NavPanel(
        {
            "\u4e8c\u6708": _FakeLocatorGroup([hidden_first, target_middle, hidden_last]),
        }
    )
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_find_date_panel", AsyncMock(return_value=panel), raising=False)

    locator = await component._find_month_leaf_locator(page, "2026-02-01")

    assert locator is target_middle
