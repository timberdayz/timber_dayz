from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import date, datetime, timedelta
from typing import Any

from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent


@dataclass
class RangePaneState:
    panel: Any | None
    body: Any | None
    month: tuple[int, int] | None


@dataclass
class RangePopupState:
    left: RangePaneState
    right: RangePaneState
    active_boundary: str | None


class TiktokDatePicker(DatePickerComponent):
    """Shared TikTok date picker with a products-page custom range path."""

    platform = "tiktok"
    component_type = "date_picker"
    data_domain = None

    def _page_kind(self, url: str) -> str | None:
        current = str(url or "")
        if "/compass/data-overview" in current:
            return "traffic"
        if "/compass/product-analysis" in current:
            return "products"
        if "/compass/service-analytics" in current:
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
        if option in {DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS}:
            return (current - timedelta(days=29)).isoformat(), current.isoformat()
        raise ValueError(f"unsupported date option: {option.value}")

    def _context_custom_range(self) -> tuple[str, str] | None:
        config = self.ctx.config or {}
        params = config.get("params") or {}
        for candidate in (params.get("time_selection"), config.get("time_selection")):
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
        return start_date.replace("-", "/") in normalized and end_date.replace("-", "/") in normalized

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...], timeout_ms: int = 500) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=timeout_ms):
                    return locator
            except Exception:
                continue
        return None

    async def _first_visible_in_scope(self, scope: Any, selectors: tuple[str, ...], timeout_ms: int = 500) -> Any | None:
        for selector in selectors:
            try:
                locator = scope.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=timeout_ms):
                    return locator
            except Exception:
                continue
        return None

    async def _pick_visible_locator(self, match_group: Any, *, timeout_ms: int = 300) -> Any | None:
        if match_group is None:
            return None

        candidates: list[Any] = []
        try:
            if hasattr(match_group, "count") and hasattr(match_group, "nth"):
                count = await match_group.count()
                for idx in range(count):
                    candidates.append(match_group.nth(idx))
        except Exception:
            pass

        if hasattr(match_group, "last"):
            candidates.append(match_group.last)
        if hasattr(match_group, "first"):
            candidates.append(match_group.first)
        elif not candidates:
            candidates.append(match_group)

        seen: set[int] = set()
        for locator in candidates:
            if locator is None:
                continue
            marker = id(locator)
            if marker in seen:
                continue
            seen.add(marker)
            try:
                if await locator.is_visible(timeout=timeout_ms):
                    return locator
            except Exception:
                continue
        return None

    async def _panel_scope(self, page: Any, pane: str) -> Any | None:
        panel_candidates: list[tuple[float, Any]] = []
        seen_panel_keys: set[tuple[int, int]] = set()
        for selector in (
            '[class*="panel-date-inner"]',
            '[class*="panel-week-inner"]',
        ):
            try:
                group = page.locator(selector)
                count = await group.count()
                for idx in range(count):
                    locator = group.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    try:
                        bbox = await locator.bounding_box()
                    except Exception:
                        bbox = None
                    if not isinstance(bbox, dict) or not isinstance(bbox.get("x"), (int, float)):
                        continue
                    width = float(bbox.get("width") or 0.0)
                    panel_key = (round(float(bbox["x"])), round(width))
                    if panel_key in seen_panel_keys:
                        continue
                    seen_panel_keys.add(panel_key)
                    panel_candidates.append((float(bbox["x"]), locator))
            except Exception:
                continue

        if len(panel_candidates) >= 2:
            panel_candidates.sort(key=lambda item: item[0])
            panels = [locator for _, locator in panel_candidates[:2]]
            pane_index = 0 if pane == "left" else 1
            if pane_index >= len(panels):
                pane_index = len(panels) - 1
            return panels[pane_index]

        scored_panels: list[tuple[tuple[int, int, int], float | None, Any]] = []
        seen_keys: set[str] = set()
        for selector in (
            ".theme-arco-picker-panel",
            ".arco-picker-panel",
            '[class*="picker-panel"]',
            '.arco-picker-range-wrapper > *',
            '.arco-picker-range-container > *',
            '[class*="picker-range-wrapper"] > *',
            '[class*="picker-range-container"] > *',
        ):
            try:
                group = page.locator(selector)
                count = await group.count()
                for idx in range(count):
                    locator = group.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    try:
                        panel_text = await locator.inner_text()
                    except Exception:
                        panel_text = ""
                    panel_key = re.sub(r"\s+", " ", str(panel_text or "").strip())
                    if panel_key and panel_key in seen_keys:
                        continue
                    header_count = 0
                    cell_count = 0
                    try:
                        headers = locator.locator('[class*="header-value"]')
                        header_count = await headers.count()
                    except Exception:
                        header_count = 0
                    try:
                        cells = locator.locator('[class*="picker-cell"]')
                        cell_count = await cells.count()
                    except Exception:
                        cell_count = 0
                    bbox_x: float | None = None
                    try:
                        bbox = await locator.bounding_box()
                    except Exception:
                        bbox = None
                    if isinstance(bbox, dict):
                        raw_x = bbox.get("x")
                        if isinstance(raw_x, (int, float)):
                            bbox_x = float(raw_x)
                    score = (
                        1 if header_count == 1 else 0,
                        1 if cell_count >= 20 else 0,
                        len(panel_key),
                        -header_count,
                    )
                    scored_panels.append((score, bbox_x, locator))
                    if panel_key:
                        seen_keys.add(panel_key)
            except Exception:
                continue

        if not scored_panels:
            return None

        panels_with_position = [item for item in scored_panels if item[1] is not None]
        if len(panels_with_position) >= 2:
            panels_with_position.sort(key=lambda item: float(item[1]))
            visible_panels = [locator for _, _, locator in panels_with_position[:2]]
        else:
            scored_panels.sort(key=lambda item: item[0], reverse=True)
            visible_panels = [locator for _, _, locator in scored_panels[:2]]

        pane_index = 0 if pane == "left" else 1
        if pane_index >= len(visible_panels):
            pane_index = len(visible_panels) - 1
        return visible_panels[pane_index]

    async def _pane_body_scope(self, page: Any, pane: str) -> Any | None:
        panel = await self._panel_scope(page, pane)
        if panel is not None:
            candidate_bodies: list[tuple[tuple[int, float, float], Any]] = []
            seen_body_keys: set[tuple[int, int]] = set()
            for selector in (
                ".arco-picker-body",
                '[class*="picker-body"]',
            ):
                try:
                    group = panel.locator(selector)
                    count = await group.count()
                    for idx in range(count):
                        locator = group.nth(idx)
                        if not await locator.is_visible(timeout=300):
                            continue
                        try:
                            bbox = await locator.bounding_box()
                        except Exception:
                            bbox = None
                        if not isinstance(bbox, dict) or not isinstance(bbox.get("x"), (int, float)):
                            continue
                        width = float(bbox.get("width") or 0.0)
                        height = float(bbox.get("height") or 0.0)
                        cell_count = 0
                        for cell_selector in (".arco-picker-cell-in-view", '[class*="cell-in-view"]'):
                            try:
                                cells = locator.locator(cell_selector)
                                cell_count = max(cell_count, await cells.count())
                            except Exception:
                                continue
                        if cell_count <= 0 and width < 100:
                            continue
                        width = float(bbox.get("width") or 0.0)
                        body_key = (round(float(bbox["x"])), round(width))
                        if body_key in seen_body_keys:
                            continue
                        seen_body_keys.add(body_key)
                        score = (cell_count, width, height)
                        candidate_bodies.append((score, locator))
                except Exception:
                    continue
            if candidate_bodies:
                candidate_bodies.sort(key=lambda item: item[0], reverse=True)
                return candidate_bodies[0][1]

        candidate_bodies: list[tuple[float, Any]] = []
        seen_body_keys: set[tuple[int, int]] = set()
        for selector in (
            ".arco-picker-body",
            '[class*="picker-body"]',
            '.arco-picker-panel table',
            '[class*="picker-panel"] table',
        ):
            try:
                group = page.locator(selector)
                count = await group.count()
                for idx in range(count):
                    locator = group.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    try:
                        bbox = await locator.bounding_box()
                    except Exception:
                        bbox = None
                    if not isinstance(bbox, dict) or not isinstance(bbox.get("x"), (int, float)):
                        continue
                    width = float(bbox.get("width") or 0.0)
                    body_key = (round(float(bbox["x"])), round(width))
                    if body_key in seen_body_keys:
                        continue
                    seen_body_keys.add(body_key)
                    candidate_bodies.append((float(bbox["x"]), locator))
            except Exception:
                continue

        if candidate_bodies:
            candidate_bodies.sort(key=lambda item: item[0])
            bodies = [locator for _, locator in candidate_bodies[:2]]
            pane_index = 0 if pane == "left" else 1
            if pane_index >= len(bodies):
                pane_index = len(bodies) - 1
            return bodies[pane_index]

        return panel

    async def _year_grid_visible(self, page: Any, pane: str) -> bool:
        scope = await self._panel_scope(page, pane)
        if scope is None:
            return False

        visible_years = 0
        for year in range(2018, 2036):
            try:
                matches = scope.get_by_text(str(year), exact=True)
                if await self._pick_visible_locator(matches, timeout_ms=150) is not None:
                    visible_years += 1
                    if visible_years >= 8:
                        return True
            except Exception:
                continue
        return False

    async def _open_year_grid(self, page: Any, pane: str) -> bool:
        if await self._year_grid_visible(page, pane):
            return True

        scope = await self._panel_scope(page, pane)
        if scope is None:
            return False

        header = await self._first_visible_in_scope(
            scope,
            (
                '[class*="header-view"]',
                '[class*="header-value"]',
            ),
            timeout_ms=300,
        )
        if header is None:
            return False

        try:
            await header.click(timeout=1500)
            await page.wait_for_timeout(200)
        except Exception:
            return False

        return await self._year_grid_visible(page, pane)

    async def _select_year_in_pane(self, page: Any, pane: str, target_year: int) -> bool:
        if not await self._year_grid_visible(page, pane):
            if not await self._open_year_grid(page, pane):
                return False

        scope = await self._panel_scope(page, pane)
        if scope is None:
            return False

        try:
            matches = scope.get_by_text(str(target_year), exact=True)
            locator = await self._pick_visible_locator(matches, timeout_ms=300)
            if locator is None:
                return False
            await locator.click(timeout=1500)
            await page.wait_for_timeout(200)
            return True
        except Exception:
            return False

    async def _current_summary_text(self, page: Any) -> str | None:
        selectors = (
            '#page-title-datepicker [data-tid="m4b_date_picker_range_picker"]',
            '[data-tid="m4b_date_picker_range_picker"]',
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            "div.theme-arco-picker-range",
            "div.arco-picker-range",
            "div.theme-arco-picker",
            "div.arco-picker",
            "div.theme-arco-picker-input",
            "div.arco-picker-input",
        )
        locator = await self._first_visible_locator(page, selectors, timeout_ms=300)
        if locator is None:
            return None

        text_fragments: list[str] = []
        for reader in ("text_content", "inner_text"):
            try:
                value = await getattr(locator, reader)()
                if value:
                    text_fragments.append(str(value))
            except Exception:
                continue

        for selector in (".arco-picker-input", "input"):
            try:
                inputs = locator.locator(selector)
                count = await inputs.count()
                for idx in range(count):
                    input_locator = inputs.nth(idx)
                    try:
                        if not await input_locator.is_visible(timeout=150):
                            continue
                    except Exception:
                        continue
                    try:
                        value = await input_locator.input_value()
                    except Exception:
                        value = ""
                    if value:
                        text_fragments.append(str(value))
            except Exception:
                continue

        normalized = " ".join(fragment.strip() for fragment in text_fragments if str(fragment).strip())
        return normalized or None

    async def _range_locator(self, page: Any) -> Any | None:
        selectors = (
            '#page-title-datepicker [data-tid="m4b_date_picker_range_picker"]',
            '[data-tid="m4b_date_picker_range_picker"]',
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            "div.theme-arco-picker-range",
            "div.arco-picker-range",
            "div.theme-arco-picker",
            "div.arco-picker",
        )
        return await self._first_visible_locator(page, selectors, timeout_ms=300)

    async def _current_range_inputs(self, page: Any) -> tuple[str | None, str | None]:
        locator = await self._range_locator(page)
        if locator is None:
            return None, None

        values: list[str | None] = []
        try:
            inputs = locator.locator("input")
            count = await inputs.count()
            for idx in range(min(count, 2)):
                input_locator = inputs.nth(idx)
                try:
                    if not await input_locator.is_visible(timeout=150):
                        values.append(None)
                        continue
                except Exception:
                    values.append(None)
                    continue
                try:
                    values.append(str(await input_locator.input_value() or "").strip() or None)
                except Exception:
                    values.append(None)
        except Exception:
            return None, None

        while len(values) < 2:
            values.append(None)
        return values[0], values[1]

    async def _active_boundary(self, page: Any) -> str | None:
        locator = await self._range_locator(page)
        if locator is None:
            return None

        html = ""
        for reader in ("inner_html", "inner_text", "text_content"):
            try:
                html = str(await getattr(locator, reader)() or "")
                if html:
                    break
            except Exception:
                continue
        if not html:
            return None

        matches = re.findall(
            r'arco-picker-input([^"]*)".*?<input[^>]*value="([^"]*)"',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(matches) >= 2:
            if "active" in matches[0][0]:
                return "start"
            if "active" in matches[1][0]:
                return "end"
        return None

    async def _wait_boundary_active(
        self,
        page: Any,
        boundary: str,
        *,
        timeout_ms: int = 1200,
        poll_ms: int = 150,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            if await self._active_boundary(page) == boundary:
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _wait_input_value(
        self,
        page: Any,
        boundary: str,
        expected_value: str,
        *,
        timeout_ms: int = 1200,
        poll_ms: int = 150,
    ) -> bool:
        normalized_expected = expected_value.replace("-", "/")
        waited = 0
        while waited <= timeout_ms:
            start_value, end_value = await self._current_range_inputs(page)
            current = start_value if boundary == "start" else end_value
            if str(current or "").strip() == normalized_expected:
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _panel_open(self, page: Any) -> bool:
        for selector in (
            "[data-testid='time-selector-last-7-days']",
            "[data-testid='time-selector-last-28-days']",
            "button:has-text('\u4eca\u5929')",
            "button:has-text('\u6700\u8fd17 \u5929')",
            "button:has-text('\u6700\u8fd128 \u5929')",
            "div[role='tab']:has-text('\u81ea\u5b9a\u4e49')",
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

        if await self._year_grid_visible(page, "left") or await self._year_grid_visible(page, "right"):
            return True
        return False

    async def _open_panel(self, page: Any) -> bool:
        if await self._panel_open(page):
            return True

        for selector in (
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            "div.theme-arco-picker-range",
            "div.arco-picker-range",
            ".theme-arco-picker",
            ".arco-picker",
        ):
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=500):
                    await locator.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    if await self._panel_open(page):
                        return True
            except Exception:
                continue
        return False

    async def _focus_range_input(self, page: Any, which: str) -> bool:
        index = 0 if which == "start" else 1
        for selector in (
            '#page-title-datepicker [data-tid="m4b_date_picker_range_picker"] input',
            '[data-tid="m4b_date_picker_range_picker"] input',
            'div.theme-arco-picker.theme-arco-picker-range input',
            'div.arco-picker.arco-picker-range input',
            'div.theme-arco-picker-range input',
            'div.arco-picker-range input',
        ):
            try:
                inputs = page.locator(selector)
                if await inputs.count() <= index:
                    continue
                locator = inputs.nth(index)
                if not await locator.is_visible(timeout=300):
                    continue
                await locator.click(timeout=1500)
                await page.wait_for_timeout(200)
                return True
            except Exception:
                continue
        return False

    async def _select_start_input(self, page: Any) -> bool:
        return await self._focus_range_input(page, "start")

    async def _select_end_input(self, page: Any) -> bool:
        return await self._focus_range_input(page, "end")

    def _parse_month_header(self, text: str | None) -> tuple[int, int] | None:
        value = str(text or "").strip()
        if not value:
            return None
        match = re.search(r"(20\d{2})\D+?(\d{1,2})\D*", value)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    async def _panel_header_text(self, panel: Any) -> str | None:
        header = await self._first_visible_in_scope(
            panel,
            (
                '[class*="picker-header"]',
                '[class*="header-view"]',
                '[class*="header-value"]',
            ),
            timeout_ms=300,
        )
        if header is None:
            return None

        text_chunks: list[str] = []
        for reader in ("inner_text", "text_content"):
            try:
                value = await getattr(header, reader)()
                if value:
                    text_chunks.append(str(value))
            except Exception:
                continue

        try:
            year_matches = header.get_by_text(re.compile(r"20\d{2}"), exact=False)
            year_locator = await self._pick_visible_locator(year_matches, timeout_ms=150)
            if year_locator is not None:
                text_chunks.append(await year_locator.inner_text())
        except Exception:
            pass

        try:
            month_matches = header.get_by_text(re.compile(r"\d{1,2}\D*$"), exact=False)
            month_locator = await self._pick_visible_locator(month_matches, timeout_ms=150)
            if month_locator is not None:
                text_chunks.append(await month_locator.inner_text())
        except Exception:
            pass

        normalized = " ".join(chunk.strip() for chunk in text_chunks if str(chunk).strip())
        return normalized or None

    async def _read_visible_months(self, page: Any) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        parsed_headers: list[tuple[int, int] | None] = []
        for pane in ("left", "right"):
            scope = await self._panel_scope(page, pane)
            if scope is None:
                parsed_headers.append(None)
                continue
            header_text = await self._panel_header_text(scope)
            parsed_headers.append(self._parse_month_header(header_text))
        return parsed_headers[0], parsed_headers[1]

    def _month_key(self, year: int, month: int) -> int:
        return year * 12 + month

    def _next_month(self, year: int, month: int) -> tuple[int, int]:
        if month >= 12:
            return year + 1, 1
        return year, month + 1

    async def _current_visible_header_months(self, page: Any) -> list[tuple[int, int]]:
        headers: list[tuple[int, int]] = []
        for selector in (
            ".arco-picker-header-value",
            '[class*="picker-header-value"]',
            '[class*="header-value"]',
        ):
            try:
                group = page.locator(selector)
                count = await group.count()
                for idx in range(count):
                    locator = group.nth(idx)
                    if not await locator.is_visible(timeout=300):
                        continue
                    text = None
                    for reader in ("inner_text", "text_content"):
                        try:
                            text = await getattr(locator, reader)()
                            break
                        except Exception:
                            continue
                    parsed = self._parse_month_header(text)
                    if parsed is not None and parsed not in headers:
                        headers.append(parsed)
                if len(headers) >= 2:
                    return headers[:2]
            except Exception:
                continue
        return headers

    async def _current_pane_month(self, page: Any, pane: str) -> tuple[int, int] | None:
        visible_headers = await self._current_visible_header_months(page)
        if len(visible_headers) >= 2:
            return visible_headers[0] if pane == "left" else visible_headers[1]
        if len(visible_headers) == 1:
            return visible_headers[0]

        scope = await self._panel_scope(page, pane)
        if scope is None:
            return None
        header_text = await self._panel_header_text(scope)
        return self._parse_month_header(header_text)

    async def _popup_state(self, page: Any) -> RangePopupState:
        left_panel = await self._panel_scope(page, "left")
        right_panel = await self._panel_scope(page, "right")
        left_body = await self._pane_body_scope(page, "left")
        right_body = await self._pane_body_scope(page, "right")
        left_month = await self._current_pane_month(page, "left")
        right_month = self._next_month(*left_month) if left_month is not None else await self._current_pane_month(page, "right")
        active_boundary = await self._active_boundary(page)
        return RangePopupState(
            left=RangePaneState(panel=left_panel, body=left_body, month=left_month),
            right=RangePaneState(panel=right_panel, body=right_body, month=right_month),
            active_boundary=active_boundary,
        )

    def _popup_state_has_valid_two_page_months(self, state: RangePopupState) -> bool:
        if state.left.month is None or state.left.body is None or state.right.body is None:
            return False
        if state.right.month is None:
            return False
        return state.right.month == self._next_month(*state.left.month)

    async def _pane_showing_month(self, page: Any, target_year: int, target_month: int) -> str | None:
        target = (target_year, target_month)
        left_month, right_month = await self._read_visible_months(page)
        if left_month == target:
            return "left"
        if right_month == target:
            return "right"
        left_month = await self._current_pane_month(page, "left")
        if left_month == target:
            return "left"
        right_month = await self._current_pane_month(page, "right")
        if right_month == target:
            return "right"
        return None

    async def _wait_visible_months_changed(
        self,
        page: Any,
        previous: tuple[tuple[int, int] | None, tuple[int, int] | None],
        *,
        timeout_ms: int = 1500,
        poll_ms: int = 150,
    ) -> tuple[tuple[int, int] | None, tuple[int, int] | None] | None:
        waited = 0
        while waited <= timeout_ms:
            current = await self._read_visible_months(page)
            if current != previous:
                return current
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None

    async def _wait_pane_month_changed(
        self,
        page: Any,
        pane: str,
        previous: tuple[int, int] | None,
        *,
        timeout_ms: int = 1500,
        poll_ms: int = 150,
    ) -> tuple[int, int] | None:
        waited = 0
        while waited <= timeout_ms:
            current = await self._current_pane_month(page, pane)
            if current != previous:
                return current
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None

    async def _wait_pane_month_matches_target(
        self,
        page: Any,
        pane: str,
        target: tuple[int, int],
        *,
        timeout_ms: int = 1200,
        poll_ms: int = 150,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            current = await self._current_pane_month(page, pane)
            if current == target:
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _click_month_nav(self, page: Any, direction: str) -> bool:
        pane = "left" if direction == "prev" else "right"
        scope = await self._panel_scope(page, pane)
        if scope is None:
            return False

        locator = None
        selectors = (
            '.arco-picker-header-icon:has(svg.arco-icon-left)',
            '.arco-picker-header-icon:has(svg.arco-icon-right)',
            '[class*="picker-header-icon"]:has(svg[class~="arco-icon-left"])',
            '[class*="picker-header-icon"]:has(svg[class~="arco-icon-right"])',
        )
        target_patterns = ("icon-left",) if direction == "prev" else ("icon-right",)
        reject_patterns = ("double_left", "double-right", "double_left", "double_right") if direction == "prev" else ("double_right", "double-left", "double_left", "double_right")

        for selector in selectors:
            if ("left" in selector and direction != "prev") or ("right" in selector and direction != "next"):
                continue
            try:
                candidate = scope.locator(selector).first
                if await candidate.count() > 0 and await candidate.is_visible(timeout=300):
                    locator = candidate
                    break
            except Exception:
                continue

        if locator is None:
            # Fallback: inspect visible header icons and ignore double-arrow buttons.
            for selector in (
                ".arco-picker-header-icon:not(.arco-picker-header-icon-hidden)",
                '[class*="picker-header-icon"]:not([class*="hidden"])',
                'button[class*="header-icon"]:not([class*="hidden"])',
            ):
                try:
                    group = scope.locator(selector)
                    count = await group.count()
                    for idx in range(count):
                        candidate = group.nth(idx)
                        if not await candidate.is_visible(timeout=300):
                            continue
                        markup = ""
                        try:
                            markup = (await candidate.inner_text()) or ""
                        except Exception:
                            markup = ""
                        # Prefer actual svg class names from DOM if available.
                        for reader in ("inner_html",):
                            try:
                                markup = f"{markup} {(await getattr(candidate, reader)()) or ''}"
                            except Exception:
                                continue
                        lowered = markup.lower()
                        if any(token in lowered for token in reject_patterns):
                            continue
                        if any(token in lowered for token in target_patterns):
                            locator = candidate
                            break
                    if locator is not None:
                        break
                except Exception:
                    continue

        if locator is None:
            return False
        try:
            await locator.click(timeout=1500)
            await page.wait_for_timeout(200)
            return True
        except Exception:
            return False

    async def _navigate_left_to_month(self, page: Any, target_year: int, target_month: int) -> bool:
        target_key = self._month_key(target_year, target_month)
        for _ in range(24):
            left_month = await self._current_pane_month(page, "left")
            if left_month == (target_year, target_month):
                return True
            if left_month is None:
                return False

            current_key = self._month_key(left_month[0], left_month[1])
            direction = "next" if current_key < target_key else "prev"
            if not await self._click_month_nav(page, direction):
                fallback = await self._current_pane_month(page, "left")
                return fallback == (target_year, target_month)
            updated = await self._wait_pane_month_changed(page, "left", left_month)
            if updated is None:
                if await self._wait_pane_month_matches_target(page, "left", (target_year, target_month)):
                    return True
                return False

        left_month = await self._current_pane_month(page, "left")
        return left_month == (target_year, target_month)

    async def _navigate_right_to_month(self, page: Any, target_year: int, target_month: int) -> bool:
        target_key = self._month_key(target_year, target_month)
        for _ in range(24):
            right_month = await self._current_pane_month(page, "right")
            if right_month == (target_year, target_month):
                return True
            if right_month is None:
                return False

            current_key = self._month_key(right_month[0], right_month[1])
            direction = "next" if current_key < target_key else "prev"
            if not await self._click_month_nav(page, direction):
                fallback = await self._current_pane_month(page, "right")
                return fallback == (target_year, target_month)
            updated = await self._wait_pane_month_changed(page, "right", right_month)
            if updated is None:
                if await self._wait_pane_month_matches_target(page, "right", (target_year, target_month)):
                    return True
                return False

        right_month = await self._current_pane_month(page, "right")
        return right_month == (target_year, target_month)

    async def _select_day_in_scope(self, scope: Any, day: int) -> bool:
        if scope is None:
            return False

        scope_box: dict[str, float] | None = None
        try:
            candidate_box = await scope.bounding_box()
        except Exception:
            candidate_box = None
        if isinstance(candidate_box, dict) and isinstance(candidate_box.get("x"), (int, float)):
            scope_box = {
                "x": float(candidate_box["x"]),
                "width": float(candidate_box.get("width") or 0.0),
            }

        day_text = str(day)
        for selector in (".arco-picker-cell-in-view", '[class*="cell-in-view"]'):
            try:
                in_view_scope = scope.locator(selector)
                matches = in_view_scope.get_by_text(day_text, exact=True)
                locator = await self._pick_day_locator_in_scope(matches, scope_box=scope_box, timeout_ms=300)
                if locator is None:
                    continue
                await locator.click(timeout=1500)
                return True
            except Exception:
                continue
        return False

    async def _select_day_in_pane(self, page: Any, pane: str, day: int) -> bool:
        scope = await self._pane_body_scope(page, pane)
        return await self._select_day_in_scope(scope, day)

    async def _pick_day_locator_in_scope(
        self,
        match_group: Any,
        *,
        scope_box: dict[str, float] | None,
        timeout_ms: int = 300,
    ) -> Any | None:
        candidates: list[Any] = []
        try:
            if hasattr(match_group, "count") and hasattr(match_group, "nth"):
                count = await match_group.count()
                for idx in range(count):
                    candidates.append(match_group.nth(idx))
        except Exception:
            pass

        filtered: list[tuple[float, Any]] = []
        if scope_box is not None:
            left_edge = float(scope_box.get("x") or 0.0)
            right_edge = left_edge + float(scope_box.get("width") or 0.0)
            for locator in candidates:
                try:
                    if not await locator.is_visible(timeout=timeout_ms):
                        continue
                except Exception:
                    continue
                try:
                    bbox = await locator.bounding_box()
                except Exception:
                    bbox = None
                if not isinstance(bbox, dict) or not isinstance(bbox.get("x"), (int, float)):
                    continue
                cell_left = float(bbox["x"])
                cell_right = cell_left + float(bbox.get("width") or 0.0)
                if cell_left >= left_edge and cell_right <= right_edge:
                    filtered.append((cell_left, locator))
            if filtered:
                filtered.sort(key=lambda item: item[0])
                return filtered[0][1]

        return await self._pick_visible_locator(match_group, timeout_ms=timeout_ms)

    async def _select_start_day_on_left(self, page: Any, day: int) -> bool:
        return await self._select_day_in_pane(page, "left", day)

    async def _select_end_day_on_left(self, page: Any, day: int) -> bool:
        return await self._select_day_in_pane(page, "left", day)

    async def _select_end_day_on_right(self, page: Any, day: int) -> bool:
        return await self._select_day_in_pane(page, "right", day)

    async def _select_start_date_from_state(self, state: RangePopupState, target: datetime) -> bool:
        if state.left.month != (target.year, target.month):
            return False
        return await self._select_day_in_scope(state.left.body, target.day)

    async def _select_end_date_from_state(
        self,
        state: RangePopupState,
        *,
        start_value: datetime,
        end_value: datetime,
    ) -> bool:
        same_month = (start_value.year, start_value.month) == (end_value.year, end_value.month)
        target_pane = state.left if same_month else state.right
        if target_pane.month != (end_value.year, end_value.month):
            return False
        return await self._select_day_in_scope(target_pane.body, end_value.day)

    async def _confirm_range_applied(
        self,
        page: Any,
        *,
        start_date: str,
        end_date: str,
        timeout_ms: int = 3000,
        poll_ms: int = 300,
    ) -> bool:
        elapsed = 0
        while elapsed <= timeout_ms:
            start_value, end_value = await self._current_range_inputs(page)
            if (
                str(start_value or "").strip() == start_date.replace("-", "/")
                and str(end_value or "").strip() == end_date.replace("-", "/")
            ):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
        return False

    async def _current_range_matches(self, page: Any, option: DateOption) -> bool:
        start_date, end_date = self._resolve_range_for_context(option)
        start_value, end_value = await self._current_range_inputs(page)
        return (
            str(start_value or "").strip() == start_date.replace("-", "/")
            and str(end_value or "").strip() == end_date.replace("-", "/")
        )

    def _quick_selector(self, option: DateOption) -> str | None:
        kind = getattr(self, "_current_page_kind", None)
        if kind == "services":
            if option == DateOption.LAST_7_DAYS:
                return 'button:has-text("\u6700\u8fd17 \u5929")'
            if option in {DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS}:
                return 'button:has-text("\u6700\u8fd128 \u5929")'

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
        if await self._current_range_matches(page, option):
            return DatePickResult(success=True, message="ok", option=option)

        if not await self._open_panel(page):
            return DatePickResult(success=False, message="failed to open date picker panel", option=option)

        start_value = datetime.strptime(start_date, "%Y-%m-%d")
        end_value = datetime.strptime(end_date, "%Y-%m-%d")

        same_month_range = (
            start_value.year == end_value.year
            and start_value.month == end_value.month
        )

        if not await self._select_start_input(page):
            return DatePickResult(success=False, message="failed to focus start date input", option=option)
        if not await self._wait_boundary_active(page, "start"):
            return DatePickResult(success=False, message="failed to activate start date input", option=option)

        if not await self._navigate_left_to_month(page, start_value.year, start_value.month):
            return DatePickResult(success=False, message="failed to navigate left page to start month", option=option)

        start_state = await self._popup_state(page)
        if not self._popup_state_has_valid_two_page_months(start_state):
            return DatePickResult(success=False, message="invalid two-page calendar state", option=option)

        if same_month_range:
            if not await self._select_start_date_from_state(start_state, start_value):
                return DatePickResult(success=False, message="failed to select start day on left page", option=option)
            if not await self._wait_input_value(page, "start", start_date):
                return DatePickResult(success=False, message="failed to apply start date", option=option)
            if not await self._select_end_input(page):
                return DatePickResult(success=False, message="failed to focus end date input", option=option)
            if not await self._wait_boundary_active(page, "end"):
                return DatePickResult(success=False, message="failed to activate end date input", option=option)
            end_state = await self._popup_state(page)
            if not self._popup_state_has_valid_two_page_months(end_state):
                return DatePickResult(success=False, message="invalid two-page calendar state", option=option)
            if not await self._select_end_date_from_state(
                end_state,
                start_value=start_value,
                end_value=end_value,
            ):
                return DatePickResult(success=False, message="failed to select end day on left page", option=option)
        else:
            if not await self._select_start_date_from_state(start_state, start_value):
                return DatePickResult(success=False, message="failed to select start day on left page", option=option)
            if not await self._wait_input_value(page, "start", start_date):
                return DatePickResult(success=False, message="failed to apply start date", option=option)
            if not await self._select_end_input(page):
                return DatePickResult(success=False, message="failed to focus end date input", option=option)
            if not await self._wait_boundary_active(page, "end"):
                return DatePickResult(success=False, message="failed to activate end date input", option=option)
            if not await self._navigate_right_to_month(page, end_value.year, end_value.month):
                return DatePickResult(success=False, message="failed to navigate right page to end month", option=option)
            end_state = await self._popup_state(page)
            if not self._popup_state_has_valid_two_page_months(end_state):
                return DatePickResult(success=False, message="invalid two-page calendar state", option=option)
            if not await self._select_end_date_from_state(
                end_state,
                start_value=start_value,
                end_value=end_value,
            ):
                return DatePickResult(success=False, message="failed to select end day on right page", option=option)
        if not await self._wait_input_value(page, "end", end_date):
            return DatePickResult(success=False, message="failed to apply end date", option=option)
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
