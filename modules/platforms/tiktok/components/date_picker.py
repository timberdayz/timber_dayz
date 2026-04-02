from __future__ import annotations

from typing import Any

from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent


class TiktokDatePicker(DatePickerComponent):
    """Shared TikTok date picker for traffic/products pages.

    The current recording evidence shows that `data-overview` and
    `product-analysis` use the same Arco-style range picker with quick-range
    shortcuts. `service-analytics` uses a different panel and is intentionally
    left out of this helper for now.
    """

    platform = "tiktok"
    component_type = "date_picker"
    data_domain = None

    def _page_kind(self, url: str) -> str | None:
        cur = str(url or "")
        if "/compass/data-overview" in cur:
            return "traffic"
        if "/compass/product-analysis" in cur:
            return "products"
        if "/compass/service-analytics" in cur:
            return "services"
        return None

    async def _panel_open(self, page: Any) -> bool:
        for selector in (
            ".theme-arco-picker-dropdown",
            ".arco-picker-dropdown",
            "[data-testid='time-selector-last-7-days']",
            "[data-testid='time-selector-last-28-days']",
        ):
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=300):
                    return True
            except Exception:
                continue
        return False

    async def _open_panel(self, page: Any) -> bool:
        if await self._panel_open(page):
            return True

        if self._page_kind(str(getattr(page, "url", "") or "")) == "services":
            for selector in (
                "button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn",
                ".theme-m4b-date-picker-range-with-mode-shortcut-custom",
                'button:has-text("近7天")',
                'button:has-text("近28天")',
            ):
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=500):
                        await locator.click(timeout=1500)
                        await page.wait_for_timeout(300)
                        return True
                except Exception:
                    continue
            return False

        for selector in (
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            ".theme-arco-picker",
            ".arco-picker",
        ):
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=500):
                    await locator.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    return await self._panel_open(page)
            except Exception:
                continue
        return False

    def _quick_selector(self, option: DateOption) -> str | None:
        kind = None
        # selector choice depends on page kind when service analytics uses a custom m4b picker
        if hasattr(self, "_current_page_kind"):
            kind = getattr(self, "_current_page_kind")
        if kind == "services":
            if option == DateOption.LAST_7_DAYS:
                return 'button:has-text("近7天")'
            if option == DateOption.LAST_28_DAYS:
                return 'button:has-text("近28天")'

        if option == DateOption.LAST_7_DAYS:
            return "[data-testid='time-selector-last-7-days']"
        if option == DateOption.LAST_28_DAYS:
            return "[data-testid='time-selector-last-28-days']"
        return None

    async def _current_option(self, page: Any) -> DateOption | None:
        for option in (DateOption.LAST_7_DAYS, DateOption.LAST_28_DAYS):
            selector = self._quick_selector(option)
            if not selector:
                continue
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=300):
                    return option
            except Exception:
                continue
        return None

    async def _confirm_option_applied(self, page: Any, option: DateOption) -> bool:
        current = await self._current_option(page)
        return current == option

    async def _apply_quick_option(self, page: Any, option: DateOption) -> bool:
        selector = self._quick_selector(option)
        if not selector:
            return False

        try:
            locator = page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible(timeout=500):
                await locator.click(timeout=1500)
                await page.wait_for_timeout(300)
                return True
        except Exception:
            return False
        return False

    async def run(self, page: Any, option: DateOption) -> DatePickResult:
        kind = self._page_kind(str(getattr(page, "url", "") or ""))
        if kind not in {"traffic", "products"}:
            if kind != "services":
                return DatePickResult(success=False, message="unsupported page for shared tiktok date picker", option=option)

        if option not in {DateOption.LAST_7_DAYS, DateOption.LAST_28_DAYS}:
            return DatePickResult(success=False, message=f"unsupported quick date option: {option.value}", option=option)

        self._current_page_kind = kind
        if await self._current_option(page) == option:
            return DatePickResult(success=True, message="ok", option=option)

        if not await self._open_panel(page):
            return DatePickResult(success=False, message="failed to open date picker panel", option=option)

        if not await self._apply_quick_option(page, option):
            return DatePickResult(success=False, message="failed to apply quick date option", option=option)

        if not await self._confirm_option_applied(page, option):
            return DatePickResult(success=False, message="failed to confirm quick date option", option=option)

        return DatePickResult(success=True, message="ok", option=option)
