from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent


class TiktokDatePicker(DatePickerComponent):
    """Shared TikTok date picker with a product-specific custom range path."""

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

    def _resolve_range(self, option: DateOption, today: date | None = None) -> tuple[str, str]:
        current = today or date.today()
        if option == DateOption.TODAY_REALTIME:
            target = current
            return target.isoformat(), target.isoformat()
        if option == DateOption.YESTERDAY:
            target = current - timedelta(days=1)
            return target.isoformat(), target.isoformat()
        if option == DateOption.LAST_7_DAYS:
            return (current - timedelta(days=6)).isoformat(), current.isoformat()
        if option == DateOption.LAST_30_DAYS:
            return (current - timedelta(days=29)).isoformat(), current.isoformat()
        if option == DateOption.LAST_28_DAYS:
            return (current - timedelta(days=29)).isoformat(), current.isoformat()
        raise ValueError(f"unsupported date option: {option.value}")

    def _context_custom_range(self) -> tuple[str, str] | None:
        config = self.ctx.config or {}
        params = config.get("params") or {}
        for candidate in (
            params.get("time_selection"),
            config.get("time_selection"),
        ):
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("mode") or "").strip().lower() != "custom":
                continue
            start_date = str(candidate.get("start_date") or "").strip()
            end_date = str(candidate.get("end_date") or "").strip()
            if start_date and end_date:
                return start_date, end_date
        return None

    def _resolve_range_for_context(self, option: DateOption, today: date | None = None) -> tuple[str, str]:
        custom_range = self._context_custom_range()
        if custom_range is not None:
            return custom_range
        return self._resolve_range(option, today=today)

    def _summary_matches(self, summary: str | None, *, start_date: str, end_date: str) -> bool:
        text = str(summary or "").strip()
        if not text:
            return False
        normalized = re.sub(r"\s+", "", text)
        start_slash = start_date.replace("-", "/")
        end_slash = end_date.replace("-", "/")
        return start_slash in normalized and end_slash in normalized

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...], timeout_ms: int = 500) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=timeout_ms):
                    return locator
            except Exception:
                continue
        return None

    async def _current_summary_text(self, page: Any) -> str | None:
        selectors = (
            "div.theme-arco-picker",
            "div.arco-picker",
            "div.theme-arco-picker-range",
            "div.arco-picker-range",
            "input[placeholder='开始日期']",
        )
        locator = await self._first_visible_locator(page, selectors, timeout_ms=300)
        if locator is None:
            return None
        for reader in ("text_content", "inner_text"):
            try:
                return await getattr(locator, reader)()
            except Exception:
                continue
        return None

    async def _panel_open(self, page: Any) -> bool:
        for selector in (
            ".theme-arco-picker-dropdown",
            ".arco-picker-dropdown",
            '[class*="picker-dropdown"]',
            '[class*="picker-panel"]',
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

        for selector in (
            "input[placeholder='开始日期']",
            "input[placeholder='结束日期']",
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

    def _parse_month_header(self, text: str | None) -> tuple[int, int] | None:
        value = str(text or "").strip()
        if not value:
            return None
        match = re.search(r"(20\d{2})\D+?(\d{1,2})\D*月?", value)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    async def _read_visible_months(self, page: Any) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        headers: list[tuple[int, int] | None] = []
        for selector in (
            '[class*="picker-header"] [class*="header-view"]',
            '[class*="picker-panel"] [class*="header-view"]',
            '[class*="picker"] [class*="month"]',
        ):
            try:
                group = page.locator(selector)
                count = await group.count()
                for idx in range(count):
                    locator = group.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    text = None
                    for reader in ("text_content", "inner_text"):
                        try:
                            text = await getattr(locator, reader)()
                            break
                        except Exception:
                            continue
                    parsed = self._parse_month_header(text)
                    if parsed is not None:
                        headers.append(parsed)
                if len(headers) >= 2:
                    return headers[0], headers[1]
            except Exception:
                continue
        return None, None

    def _month_key(self, year: int, month: int) -> int:
        return year * 12 + month

    async def _click_month_nav(self, page: Any, pane: str, direction: str) -> bool:
        pane_index = 0 if pane == "left" else 1
        arrow = "prev" if direction == "prev" else "next"
        selectors = (
            f'[class*="picker-panel"]:nth-of-type({pane_index + 1}) [class*="header-{arrow}-btn"]',
            f'[class*="picker-panel"]:nth-of-type({pane_index + 1}) button[class*="{arrow}"]',
        )
        locator = await self._first_visible_locator(page, selectors, timeout_ms=300)
        if locator is None:
            return False
        try:
            await locator.click(timeout=1500)
            await page.wait_for_timeout(200)
            return True
        except Exception:
            return False

    async def _navigate_pane_to_month(self, page: Any, pane: str, target_year: int, target_month: int) -> bool:
        for _ in range(24):
            left_month, right_month = await self._read_visible_months(page)
            current = left_month if pane == "left" else right_month
            if current == (target_year, target_month):
                return True
            if current is None:
                return False
            current_key = self._month_key(current[0], current[1])
            target_key = self._month_key(target_year, target_month)
            direction = "prev" if current_key > target_key else "next"
            if not await self._click_month_nav(page, pane, direction):
                return False
        return False

    async def _navigate_left_to_month(self, page: Any, target_year: int, target_month: int) -> bool:
        return await self._navigate_pane_to_month(page, "left", target_year, target_month)

    async def _navigate_right_to_month(self, page: Any, target_year: int, target_month: int) -> bool:
        return await self._navigate_pane_to_month(page, "right", target_year, target_month)

    async def _select_day_in_pane(self, page: Any, pane: str, day: int) -> bool:
        pane_index = 0 if pane == "left" else 1
        selectors = (
            f'[class*="picker-panel"]:nth-of-type({pane_index + 1}) .arco-picker-cell-in-view',
            f'[class*="picker-panel"]:nth-of-type({pane_index + 1}) [class*="cell-in-view"]',
        )
        day_text = str(day)
        for selector in selectors:
            try:
                scope = page.locator(selector)
                matches = scope.get_by_text(day_text, exact=True)
                count = await matches.count()
                for idx in range(count):
                    locator = matches.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    await locator.click(timeout=1500)
                    await page.wait_for_timeout(200)
                    return True
            except Exception:
                continue
        return False

    async def _select_start_day_on_left(self, page: Any, day: int) -> bool:
        return await self._select_day_in_pane(page, "left", day)

    async def _select_end_day_on_right(self, page: Any, day: int) -> bool:
        return await self._select_day_in_pane(page, "right", day)

    async def _confirm_range_applied(self, page: Any, *, start_date: str, end_date: str, timeout_ms: int = 3000, poll_ms: int = 300) -> bool:
        elapsed = 0
        while elapsed <= timeout_ms:
            summary = await self._current_summary_text(page)
            if self._summary_matches(summary, start_date=start_date, end_date=end_date):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
        return False

    async def _current_range_matches(self, page: Any, option: DateOption) -> bool:
        start_date, end_date = self._resolve_range_for_context(option)
        summary = await self._current_summary_text(page)
        return self._summary_matches(summary, start_date=start_date, end_date=end_date)

    def _quick_selector(self, option: DateOption) -> str | None:
        kind = None
        if hasattr(self, "_current_page_kind"):
            kind = getattr(self, "_current_page_kind")
        if kind == "services":
            if option == DateOption.LAST_7_DAYS:
                return 'button:has-text("杩?澶?)'
            if option in {DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS}:
                return 'button:has-text("杩?8澶?)'

        if option == DateOption.LAST_7_DAYS:
            return "[data-testid='time-selector-last-7-days']"
        if option in {DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS}:
            return "[data-testid='time-selector-last-28-days']"
        return None

    async def _current_option(self, page: Any) -> DateOption | None:
        for option in (DateOption.LAST_7_DAYS, DateOption.LAST_30_DAYS):
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

    async def _run_products_range(self, page: Any, option: DateOption) -> DatePickResult:
        start_date, end_date = self._resolve_range_for_context(option)
        current_summary = await self._current_summary_text(page)
        if self._summary_matches(current_summary, start_date=start_date, end_date=end_date):
            return DatePickResult(success=True, message="ok", option=option)

        if not await self._open_panel(page):
            return DatePickResult(success=False, message="failed to open date picker panel", option=option)

        start_year, start_month, start_day = datetime.strptime(start_date, "%Y-%m-%d").year, datetime.strptime(start_date, "%Y-%m-%d").month, datetime.strptime(start_date, "%Y-%m-%d").day
        end_year, end_month, end_day = datetime.strptime(end_date, "%Y-%m-%d").year, datetime.strptime(end_date, "%Y-%m-%d").month, datetime.strptime(end_date, "%Y-%m-%d").day

        if not await self._navigate_left_to_month(page, start_year, start_month):
            return DatePickResult(success=False, message="failed to navigate left page to start month", option=option)
        if not await self._navigate_right_to_month(page, end_year, end_month):
            return DatePickResult(success=False, message="failed to navigate right page to end month", option=option)
        if not await self._select_start_day_on_left(page, start_day):
            return DatePickResult(success=False, message="failed to select start day on left page", option=option)
        if not await self._select_end_day_on_right(page, end_day):
            return DatePickResult(success=False, message="failed to select end day on right page", option=option)
        if not await self._confirm_range_applied(page, start_date=start_date, end_date=end_date):
            return DatePickResult(success=False, message="failed to confirm date range", option=option)
        return DatePickResult(success=True, message="ok", option=option)

    async def run(self, page: Any, option: DateOption) -> DatePickResult:
        kind = self._page_kind(str(getattr(page, "url", "") or ""))
        if kind == "products":
            return await self._run_products_range(page, option)

        if kind not in {"traffic", "services"}:
            return DatePickResult(success=False, message="unsupported page for shared tiktok date picker", option=option)

        if option not in {DateOption.LAST_7_DAYS, DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS}:
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
