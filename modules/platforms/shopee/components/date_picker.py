from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import re
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent
from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    normalize_time_request,
    preset_label,
)
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_config import ServicesSelectors


class ShopeeDatePicker(DatePickerComponent):
    platform = "shopee"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)
        cfg = self.ctx.config or {}
        domain = str(cfg.get("data_domain") or "products").strip().lower()
        self.data_domain = domain
        subtype = str(
            cfg.get("services_subtype")
            or cfg.get("sub_domain")
            or ""
        ).strip().lower()
        service_selectors = ServicesSelectors()

        overview_path = build_domain_path("products")
        if domain == "analytics":
            overview_path = build_domain_path("analytics")
        elif domain == "services" and subtype in service_selectors.service_paths:
            overview_path = service_selectors.service_paths[subtype]

        selectors = replace(ProductsSelectors(), overview_path=overview_path)
        self._delegate = ShopeeProductsExport(self.ctx, selectors=selectors)
        self.sel = self._delegate.sel
        self.service_sel = service_selectors
        self._delegate.service_sel = service_selectors
        self._delegate._target_date_label = self._target_date_label  # type: ignore[method-assign]

    def _normalize_text(self, value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _normalize_date_text(self, value: str | None) -> str:
        return re.sub(r"\s+", "", str(value or "").strip().lower())

    def _build_loose_text_pattern(self, text: str):
        escaped = [re.escape(char) for char in str(text or "").strip()]
        return re.compile(r"\s*".join(escaped), re.IGNORECASE)

    def _build_month_leaf_pattern(self, text: str):
        escaped = re.escape(str(text or "").strip())
        return re.compile(rf"^\s*{escaped}\s*$")

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...]) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _pick_visible_locator(self, match_group: Any, *, timeout_ms: int = 1000) -> Any | None:
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

    def _date_trigger_fallback_texts(self) -> tuple[str, ...]:
        candidates = [
            "\u7edf\u8ba1\u65f6\u95f4",
            *self.sel.preset_labels.values(),
            *self.sel.granularity_labels.values(),
            "\u4eca\u5929",
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_text(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(candidate)
        return tuple(deduped)

    async def _find_date_picker_trigger(self, page: Any) -> Any | None:
        trigger = await self._first_visible_locator(page, self.sel.date_picker_triggers)
        if trigger is not None:
            return trigger

        for text in self._date_trigger_fallback_texts():
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=1000):
                    return locator
            except Exception:
                continue
        return None

    async def _find_date_summary_container(self, page: Any) -> Any | None:
        summary_selectors = (
            '[class*="picker"]:has-text("缁熻鏃堕棿")',
            '[class*="date"]:has-text("缁熻鏃堕棿")',
            '[class*="time"]:has-text("缁熻鏃堕棿")',
            'div:has-text("缁熻鏃堕棿")',
            'button:has-text("缁熻鏃堕棿")',
            '[role="button"]:has-text("缁熻鏃堕棿")',
        )
        locator = await self._first_visible_locator(page, summary_selectors)
        if locator is not None:
            return locator

        try:
            text_locator = page.get_by_text("缁熻鏃堕棿", exact=False).first
            if await text_locator.is_visible(timeout=1000):
                return text_locator
        except Exception:
            pass
        return None

    def _date_panel_anchor_texts(self) -> tuple[str, ...]:
        domain = str((self.ctx.config or {}).get("data_domain") or "products").strip().lower()
        anchors: list[str] = [
            self.sel.granularity_labels.get("daily", ""),
            self.sel.granularity_labels.get("weekly", ""),
            self.sel.granularity_labels.get("monthly", ""),
        ]
        if domain == "products":
            anchors.extend(
                [
                    self.sel.preset_labels.get("today_realtime", ""),
                    self.sel.preset_labels.get("yesterday", ""),
                ]
            )
        else:
            anchors.extend(
                [
                    self.sel.preset_labels.get("yesterday", ""),
                    self.sel.preset_labels.get("last_7_days", ""),
                    self.sel.preset_labels.get("last_30_days", ""),
                ]
            )
        deduped: list[str] = []
        seen: set[str] = set()
        for anchor in anchors:
            normalized = self._normalize_date_text(anchor)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(anchor)
        return tuple(deduped)

    async def _score_date_panel_candidate(
        self,
        candidate: Any,
        anchor_texts: tuple[str, ...],
    ) -> tuple[int, int]:
        try:
            text_content = await candidate.text_content() or ""
        except Exception:
            text_content = ""
        normalized_text = self._normalize_date_text(text_content)
        hits = sum(
            1
            for anchor in anchor_texts
            if anchor and self._normalize_date_text(anchor) in normalized_text
        )
        return hits, len(normalized_text)

    async def _find_date_panel(self, page: Any) -> Any | None:
        common_selectors = (
            ".arco-trigger-popup",
            ".arco-picker-dropdown",
            ".ant-picker-dropdown",
            '[class*="picker-dropdown"]',
            '[class*="dropdown"]',
            '[class*="popup"]',
            "body > div",
        )

        anchor_texts = self._date_panel_anchor_texts()

        best_panel = None
        best_score: tuple[int, int] | None = None
        for selector in common_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                for idx in range(count - 1, -1, -1):
                    candidate = locator.nth(idx)
                    if await candidate.is_visible(timeout=500):
                        score = await self._score_date_panel_candidate(candidate, anchor_texts)
                        if score[0] <= 0:
                            continue
                        if best_score is None or score > best_score:
                            best_panel = candidate
                            best_score = score
            except Exception:
                continue
        if best_panel is not None:
            return best_panel

        fallback_locators = (
            page.locator("div"),
            page.locator("ul"),
        )
        best_panel = None
        best_score = None
        for locator in fallback_locators:
            try:
                count = await locator.count()
                for idx in range(count):
                    candidate = locator.nth(idx)
                    if not await candidate.is_visible(timeout=300):
                        continue
                    score = await self._score_date_panel_candidate(candidate, anchor_texts)
                    if score[0] <= 0:
                        continue
                    if best_score is None or score > best_score:
                        best_panel = candidate
                        best_score = score
            except Exception:
                continue
        return best_panel

    async def _find_date_option_locator(self, page: Any, text: str) -> Any | None:
        panel = await self._find_date_panel(page)
        try:
            pattern = self._build_loose_text_pattern(text)
            matches = panel.get_by_text(pattern, exact=False) if panel is not None else None
        except Exception:
            matches = None

        panel_locator = await self._pick_visible_locator(matches, timeout_ms=2000)
        if panel_locator is not None:
            return panel_locator

        try:
            global_matches = page.get_by_text(pattern, exact=False)
        except Exception:
            return None
        global_locator = await self._pick_visible_locator(global_matches, timeout_ms=2000)
        if global_locator is not None:
            return global_locator
        return None

    async def _hover_text_option(self, page: Any, text: str) -> bool:
        locator = await self._find_date_option_locator(page, text)
        if locator is None:
            return False
        try:
            await locator.hover(timeout=5000)
        except Exception:
            return False
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(150)
        try:
            await locator.click(timeout=5000)
        except Exception:
            return False
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(300)
        return True

    async def _click_text_option(self, page: Any, text: str) -> bool:
        locator = await self._find_date_option_locator(page, text)
        if locator is None:
            return False
        try:
            await locator.hover(timeout=5000)
        except Exception:
            pass
        try:
            await locator.click(timeout=5000)
        except Exception:
            return False
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(900)
        return True

    async def _open_date_picker(self, page: Any) -> None:
        trigger = await self._find_date_picker_trigger(page)
        if trigger is None:
            return
        await trigger.click(timeout=5000)
        await page.wait_for_timeout(600)
        waited = 0
        while waited <= 2000:
            panel = await self._find_date_panel(page)
            if panel is not None:
                return
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(200)
            waited += 200

    def _match_known_date_label(self, value: str | None) -> str | None:
        content = self._normalize_date_text(value)
        if not content:
            return None

        for label in (
            *self.sel.preset_labels.values(),
            *self.sel.granularity_labels.values(),
        ):
            normalized_label = self._normalize_date_text(label)
            if normalized_label and normalized_label in content:
                return label

        variant_map = {
            "过去7天": (
                "过去7天",
                "过去 7 天",
                "过去7 天",
                "过去 7天",
            ),
            "过去30天": (
                "过去30天",
                "过去 30 天",
                "过去30 天",
                "过去 30天",
            ),
        }
        for canonical, variants in variant_map.items():
            normalized_variants = tuple(self._normalize_date_text(item) for item in variants)
            if any(variant and variant in content for variant in normalized_variants):
                return canonical
        return None

    def _preset_value_from_label(self, label: str | None) -> str | None:
        normalized_label = self._normalize_date_text(label)
        if not normalized_label:
            return None
        for key, value in self.sel.preset_labels.items():
            if self._normalize_date_text(value) == normalized_label:
                return key
        return None

    def _parse_summary_date_value(self, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _extract_summary_date_values(self, summary: str | None) -> tuple[str, ...]:
        text = str(summary or "")
        if not text:
            return ()
        pattern = re.compile(r"\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2}")
        values: list[str] = []
        for match in pattern.findall(text):
            parsed_value = self._parse_summary_date_value(match)
            if parsed_value:
                values.append(parsed_value)
        return tuple(values)

    def _extract_summary_month_value(self, summary: str | None) -> tuple[int, int] | None:
        text = str(summary or "").strip()
        if not text:
            return None

        compact_match = re.search(r"(20\d{2})[./-](\d{1,2})", text)
        if compact_match:
            return int(compact_match.group(1)), int(compact_match.group(2))

        zh_match = re.search(r"(20\d{2})\s*\u5e74\s*(\d{1,2})\s*\u6708", text)
        if zh_match:
            return int(zh_match.group(1)), int(zh_match.group(2))

        return None

    def _parse_date_summary(self, summary: str | None) -> dict[str, Any] | None:
        text = str(summary or "").strip()
        if not text:
            return None

        label = self._match_known_date_label(text)
        if not label:
            return None

        preset_value = self._preset_value_from_label(label)
        if preset_value is not None:
            return {
                "mode": "preset",
                "value": preset_value,
                "label": label,
            }

        normalized_label = self._normalize_date_text(label)
        if normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("monthly")):
            month_value = self._extract_summary_month_value(text)
            if month_value is not None:
                year, month = month_value
                return {
                    "mode": "monthly",
                    "year": year,
                    "month": month,
                    "label": label,
                }

        summary_dates = self._extract_summary_date_values(text)
        if normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("weekly")) and len(summary_dates) >= 2:
            return {
                "mode": "weekly",
                "start_date": summary_dates[0],
                "end_date": summary_dates[1],
                "label": label,
            }

        if normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("daily")) and summary_dates:
            return {
                "mode": "daily",
                "date": summary_dates[0],
                "label": label,
            }

        return {"label": label}

    def _selection_state_from_text(self, summary: str | None) -> dict[str, Any] | None:
        text = str(summary or "").strip()
        if not text:
            return None
        state: dict[str, Any] = {
            "raw_text": text,
            "value_text": text,
        }

        label = self._match_known_date_label(text)
        if label:
            state["label"] = label
            normalized_label = self._normalize_date_text(label)
            if normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("daily")):
                state["mode"] = "daily"
            elif normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("weekly")):
                state["mode"] = "weekly"
            elif normalized_label == self._normalize_date_text(self.sel.granularity_labels.get("monthly")):
                state["mode"] = "monthly"
            else:
                preset_value = self._preset_value_from_label(label)
                if preset_value is not None:
                    state["mode"] = "preset"
                    state["value"] = preset_value

            if label in text:
                _, _, suffix = text.partition(label)
                stripped_suffix = str(suffix or "").strip()
                if stripped_suffix:
                    state["value_text"] = stripped_suffix

        month_value = self._extract_summary_month_value(text)
        if month_value is not None:
            year, month = month_value
            state["year"] = year
            state["month"] = month
            state.setdefault("mode", "monthly")

        summary_dates = self._extract_summary_date_values(text)
        if len(summary_dates) >= 2:
            state["start_date"] = summary_dates[0]
            state["end_date"] = summary_dates[1]
            state.setdefault("mode", "weekly")
        elif len(summary_dates) == 1:
            state["date"] = summary_dates[0]
            state.setdefault("mode", "daily")

        if "mode" not in state:
            return None
        return state

    def _selection_state_matches_target(
        self,
        state: dict[str, Any] | None,
        *,
        granularity: str,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        if not state:
            return False

        normalized_granularity = self._normalize_custom_granularity(granularity)
        if normalized_granularity == "daily":
            expected_date = start_date or end_date
            return state.get("mode") == "daily" and state.get("date") == expected_date

        if normalized_granularity == "weekly":
            return (
                state.get("mode") == "weekly"
                and state.get("start_date") == start_date
            )

        if normalized_granularity == "monthly" and start_date:
            try:
                target_date = datetime.strptime(str(start_date), "%Y-%m-%d")
            except ValueError:
                target_date = None
            if target_date is None:
                return False
            return (
                state.get("mode") == "monthly"
                and state.get("year") == target_date.year
                and state.get("month") == target_date.month
            )

        return False

    async def _current_selection_state(self, page: Any) -> dict[str, Any] | None:
        summary_text = await self._current_date_summary_text(page)
        state = self._selection_state_from_text(summary_text)
        if state is not None:
            return state

        trigger_text = await self._current_date_trigger_text(page)
        return self._selection_state_from_text(trigger_text)

    async def _current_date_summary_text(self, page: Any) -> str | None:
        summary_container = await self._find_date_summary_container(page)
        if summary_container is not None:
            try:
                summary_text = await summary_container.text_content()
            except Exception:
                summary_text = None
            if summary_text and "缁熻鏃堕棿" in str(summary_text):
                return summary_text

        trigger = await self._find_date_picker_trigger(page)
        if trigger is None:
            return None
        try:
            return await trigger.text_content()
        except Exception:
            return None

    async def _current_date_trigger_text(self, page: Any) -> str | None:
        trigger = await self._find_date_picker_trigger(page)
        if trigger is None:
            return None
        try:
            return await trigger.text_content()
        except Exception:
            return None

    async def _current_date_label(self, page: Any) -> str | None:
        trigger = await self._find_date_picker_trigger(page)
        if trigger is not None:
            try:
                summary_text = await trigger.text_content()
            except Exception:
                summary_text = None
            parsed_summary = self._parse_date_summary(summary_text)
            if parsed_summary and parsed_summary.get("label"):
                return str(parsed_summary["label"])
            matched = self._match_known_date_label(summary_text)
            if matched:
                return matched

        for text in (
            *self.sel.preset_labels.values(),
            *self.sel.granularity_labels.values(),
        ):
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=500):
                    return text
            except Exception:
                continue
        return None

    def _single_day_target_value(self, config: dict[str, Any]) -> str | None:
        return (
            str(config.get("end_date") or "").strip()
            or str(config.get("date_to") or "").strip()
            or str(config.get("start_date") or "").strip()
            or str(config.get("date_from") or "").strip()
            or None
        )

    def _custom_time_selection(self, config: dict[str, Any]) -> dict[str, Any] | None:
        time_selection = config.get("time_selection")
        if not isinstance(time_selection, dict):
            return None
        if str(time_selection.get("mode") or "").strip().lower() != "custom":
            return None
        return time_selection

    def _custom_range_bounds(self, config: dict[str, Any]) -> tuple[str | None, str | None]:
        custom_selection = self._custom_time_selection(config) or {}
        start_value = (
            str(custom_selection.get("start_date") or "").strip()
            or str(config.get("start_date") or "").strip()
            or str(config.get("date_from") or "").strip()
            or None
        )
        end_value = (
            str(custom_selection.get("end_date") or "").strip()
            or str(config.get("end_date") or "").strip()
            or str(config.get("date_to") or "").strip()
            or None
        )
        return start_value, end_value

    def _month_leaf_labels(self, iso_date: str) -> tuple[str, ...]:
        try:
            target_date = datetime.strptime(str(iso_date), "%Y-%m-%d")
        except ValueError:
            return ()

        zh_months = (
            "",
            "\u4e00\u6708",
            "\u4e8c\u6708",
            "\u4e09\u6708",
            "\u56db\u6708",
            "\u4e94\u6708",
            "\u516d\u6708",
            "\u4e03\u6708",
            "\u516b\u6708",
            "\u4e5d\u6708",
            "\u5341\u6708",
            "\u5341\u4e00\u6708",
            "\u5341\u4e8c\u6708",
        )
        return (zh_months[target_date.month],)

    def _month_grid_labels(self) -> tuple[str, ...]:
        return (
            "\u4e00\u6708",
            "\u4e8c\u6708",
            "\u4e09\u6708",
            "\u56db\u6708",
            "\u4e94\u6708",
            "\u516d\u6708",
            "\u4e03\u6708",
            "\u516b\u6708",
            "\u4e5d\u6708",
            "\u5341\u6708",
            "\u5341\u4e00\u6708",
            "\u5341\u4e8c\u6708",
        )

    def _month_summary_signatures(self, iso_date: str) -> tuple[str, ...]:
        try:
            target_date = datetime.strptime(str(iso_date), "%Y-%m-%d")
        except ValueError:
            return ()

        return (
            target_date.strftime("%Y.%m"),
            target_date.strftime("%Y-%m"),
            f"{target_date.year}\u5e74{target_date.month}\u6708",
            f"{target_date.month}\u6708{target_date.year}",
            f"\u6309\u6708{target_date.strftime('%Y.%m')}",
        )

    def _normalize_custom_granularity(self, granularity: str | None) -> str:
        normalized = str(granularity or "").strip().lower()
        if normalized in {"day", "daily", "d"}:
            return "daily"
        if normalized in {"week", "weekly", "w"}:
            return "weekly"
        if normalized in {"month", "monthly", "m"}:
            return "monthly"
        return normalized

    def _date_value_signatures(self, iso_date: str | None) -> tuple[str, ...]:
        if not iso_date:
            return ()
        try:
            target_date = datetime.strptime(str(iso_date), "%Y-%m-%d")
        except ValueError:
            return ()
        return (
            target_date.strftime("%d-%m-%Y"),
            target_date.strftime("%d/%m/%Y"),
            target_date.strftime("%Y-%m-%d"),
            target_date.strftime("%Y/%m/%d"),
        )

    async def _hint_text_visible(self, page: Any, text: str) -> bool:
        try:
            locator = page.get_by_text(text, exact=False).first
            return bool(await locator.is_visible(timeout=300))
        except Exception:
            return False

    async def _selection_hints_visible(
        self,
        page: Any,
        *,
        granularity: str,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        normalized_granularity = self._normalize_custom_granularity(granularity)
        mode_label = self.sel.granularity_labels.get(normalized_granularity)
        if not mode_label or not await self._hint_text_visible(page, mode_label):
            return False

        tokens: tuple[str, ...] = ()
        if normalized_granularity == "daily":
            tokens = self._date_value_signatures(start_date or end_date)
        elif normalized_granularity == "weekly":
            tokens = self._date_value_signatures(start_date)
        elif normalized_granularity == "monthly" and start_date:
            tokens = self._month_summary_signatures(start_date)

        for token in tokens:
            if token and await self._hint_text_visible(page, token):
                return True
        return False

    def _custom_date_summary_matches(
        self,
        summary: str | None,
        *,
        granularity: str,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        normalized_summary = self._normalize_date_text(summary)
        if not normalized_summary:
            return False

        normalized_granularity = self._normalize_custom_granularity(granularity)
        if normalized_granularity == "monthly" and start_date:
            try:
                target_date = datetime.strptime(str(start_date), "%Y-%m-%d")
            except ValueError:
                target_date = None
            month_value = self._extract_summary_month_value(summary)
            if target_date is not None and month_value == (target_date.year, target_date.month):
                return True

        parsed_summary = self._parse_date_summary(summary)
        if parsed_summary and parsed_summary.get("mode"):
            if normalized_granularity == "daily":
                expected_date = start_date or end_date
                return (
                    parsed_summary.get("mode") == "daily"
                    and parsed_summary.get("date") == expected_date
                )
            if normalized_granularity == "weekly":
                return (
                    parsed_summary.get("mode") == "weekly"
                    and parsed_summary.get("start_date") == start_date
                )
            if normalized_granularity == "monthly" and start_date:
                try:
                    target_date = datetime.strptime(str(start_date), "%Y-%m-%d")
                except ValueError:
                    target_date = None
                if target_date is not None:
                    return (
                        parsed_summary.get("mode") == "monthly"
                        and parsed_summary.get("year") == target_date.year
                        and parsed_summary.get("month") == target_date.month
                    )

        expected_label = None
        if normalized_granularity in {"daily", "weekly", "monthly"}:
            expected_label = self.sel.granularity_labels.get(normalized_granularity)
        if expected_label and self._normalize_date_text(expected_label) not in normalized_summary:
            return False

        primary_signatures: list[str] = []
        if normalized_granularity == "daily":
            primary_signatures.extend(self._date_value_signatures(start_date or end_date))
        elif normalized_granularity == "weekly":
            primary_signatures.extend(self._date_value_signatures(start_date))
        elif normalized_granularity == "monthly" and start_date:
            primary_signatures.extend(self._month_summary_signatures(start_date))

        normalized_signatures = tuple(
            self._normalize_date_text(signature) for signature in primary_signatures if signature
        )
        return any(signature and signature in normalized_summary for signature in normalized_signatures)

    def _resolve_custom_target(self, config: dict[str, Any]) -> dict[str, Any]:
        granularity = str(config.get("granularity") or "").strip().lower()
        start_date, end_date = self._custom_range_bounds(config)
        target_iso_date = start_date or end_date
        if not target_iso_date:
            raise ValueError("custom date selection requires start_date")

        target_date = datetime.strptime(str(target_iso_date), "%Y-%m-%d")
        return {
            "granularity": granularity,
            "target_iso_date": target_iso_date,
            "target_year": target_date.year,
            "target_month": target_date.month,
            "target_day": target_date.day,
            "target_month_label_zh": self._month_leaf_labels(target_iso_date)[0],
            "start_date": start_date,
            "end_date": end_date,
        }

    def _calendar_month_key(self, year: int, month: int) -> int:
        return year * 12 + month

    async def _find_month_panel(self, page: Any) -> Any | None:
        common_selectors = (
            ".arco-trigger-popup",
            ".arco-picker-dropdown",
            ".ant-picker-dropdown",
            '[class*="picker-dropdown"]',
            '[class*="dropdown"]',
            '[class*="popup"]',
            "body > div",
        )

        best_panel = None
        best_score: tuple[int, int, int] | None = None
        for selector in common_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                for idx in range(count - 1, -1, -1):
                    candidate = locator.nth(idx)
                    if not await candidate.is_visible(timeout=500):
                        continue
                    try:
                        text_content = await candidate.text_content() or ""
                    except Exception:
                        text_content = ""
                    score = (
                        1 if self._parse_month_panel_year(text_content) is not None else 0,
                        sum(1 for label in self._month_grid_labels() if label in text_content),
                        len(text_content),
                    )
                    if best_score is None or score > best_score:
                        best_panel = candidate
                        best_score = score
            except Exception:
                continue
        return best_panel

    async def _find_month_panel_header(self, page: Any) -> Any | None:
        panel = await self._find_month_panel(page)
        containers = [panel] if panel is not None else [page]
        selectors = (
            ".arco-picker-header",
            ".ant-picker-header",
            '[class*="picker-header"]',
            '[class*="calendar-header"]',
            '[class*="header"]',
        )
        for container in containers:
            if container is None:
                continue
            for selector in selectors:
                try:
                    locator = container.locator(selector)
                    count = await locator.count()
                    for idx in range(count):
                        candidate = locator.nth(idx)
                        if not await candidate.is_visible(timeout=500):
                            continue
                        text_content = await candidate.text_content()
                        if self._parse_month_panel_year(text_content) is not None:
                            return candidate
                    if count > 0:
                        first = locator.first
                        if await first.is_visible(timeout=500):
                            text_content = await first.text_content()
                            if self._parse_month_panel_year(text_content) is not None:
                                return first
                except Exception:
                    continue
        return None

    async def _current_month_panel_year_text(self, page: Any) -> str | None:
        header = await self._find_month_panel_header(page)
        panel = await self._find_month_panel(page)
        containers = [header, panel, page]
        selectors = (
            ".arco-picker-header",
            ".ant-picker-header",
            '[class*="picker-header"]',
            '[class*="calendar-header"]',
            '[class*="header"]',
        )
        for container in containers:
            if container is None:
                continue
            for selector in selectors:
                try:
                    locator = container.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=500):
                        text_content = await locator.text_content()
                        if self._parse_month_panel_year(text_content) is not None:
                            return text_content
                except Exception:
                    continue
        for container in containers:
            if container is None:
                continue
            try:
                locator = await self._pick_visible_locator(container.get_by_text(re.compile(r"20\d{2}"), exact=False))
                if locator is None:
                    continue
                text_content = await locator.text_content()
                if self._parse_month_panel_year(text_content) is not None:
                    return text_content
            except Exception:
                continue
        return None

    async def _wait_month_panel_year_changed(
        self,
        page: Any,
        previous_header: str | None,
        *,
        timeout_ms: int = 1500,
        poll_ms: int = 150,
    ) -> str | None:
        previous = str(previous_header or "").strip()
        waited = 0
        while waited <= timeout_ms:
            current = await self._current_month_panel_year_text(page)
            if str(current or "").strip() and str(current or "").strip() != previous:
                return current
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None

    async def _click_month_panel_year_nav_button(self, page: Any, direction: str) -> bool:
        selector_map = {
            "prev": (
                'button[aria-label*="previous year"]',
                'button[aria-label*="previous"]',
                '.arco-picker-header-super-prev-btn',
                '.arco-picker-header-prev-btn:not([class*="super"])',
                '.ant-picker-header-super-prev-btn',
                '.ant-picker-header-prev-btn:not([class*="super"])',
                '[class*="super-prev"]',
                '[class*="prev-btn"]:not([class*="super"])',
                '[class*="prev"]:not([class*="super"])',
                '[class*="double-left"]',
            ),
            "next": (
                'button[aria-label*="next year"]',
                'button[aria-label*="next"]',
                '.arco-picker-header-super-next-btn',
                '.arco-picker-header-next-btn:not([class*="super"])',
                '.ant-picker-header-super-next-btn',
                '.ant-picker-header-next-btn:not([class*="super"])',
                '[class*="super-next"]',
                '[class*="next-btn"]:not([class*="super"])',
                '[class*="next"]:not([class*="super"])',
                '[class*="double-right"]',
            ),
        }
        header = await self._find_month_panel_header(page)
        panel = await self._find_month_panel(page)
        containers = [header, panel, page]
        for container in containers:
            if container is None:
                continue
            for selector in selector_map.get(direction, ()):
                try:
                    locator = container.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=500):
                        await locator.click(timeout=5000)
                        if hasattr(page, "wait_for_timeout"):
                            await page.wait_for_timeout(250)
                        return True
                except Exception:
                    continue
        return False

    async def _find_month_grid_cell(self, page: Any, month_label: str) -> Any | None:
        panel = await self._find_month_panel(page)
        containers = [panel, page] if panel is not None else [page]
        pattern = self._build_month_leaf_pattern(month_label)
        for container in containers:
            if container is None:
                continue
            try:
                locator = await self._pick_visible_locator(container.get_by_text(pattern, exact=False))
                if locator is not None:
                    return locator
            except Exception:
                continue
        for container in containers:
            if container is None:
                continue
            try:
                locator = await self._pick_visible_locator(container.get_by_text(month_label, exact=True))
                if locator is not None:
                    return locator
            except Exception:
                continue
        return None

    def _parse_calendar_header_month_year_zh(self, header_text: str | None) -> tuple[int, int] | None:
        text = str(header_text or "").strip()
        if not text:
            return None

        year_match = re.search(r"(20\d{2})", text)
        if not year_match:
            return None
        year = int(year_match.group(1))

        month_match = re.search(r"(\d{1,2})\s*\u6708", text)
        if month_match:
            return year, int(month_match.group(1))

        month_year_numeric_match = re.search(r"(\d{1,2})\s*\u6708\s*(20\d{2})", text)
        if month_year_numeric_match:
            return int(month_year_numeric_match.group(2)), int(month_year_numeric_match.group(1))

        month_labels = (
            ("\u5341\u4e00\u6708", 11),
            ("\u5341\u4e8c\u6708", 12),
            ("\u5341\u6708", 10),
            ("\u4e00\u6708", 1),
            ("\u4e8c\u6708", 2),
            ("\u4e09\u6708", 3),
            ("\u56db\u6708", 4),
            ("\u4e94\u6708", 5),
            ("\u516d\u6708", 6),
            ("\u4e03\u6708", 7),
            ("\u516b\u6708", 8),
            ("\u4e5d\u6708", 9),
            ("january", 1),
            ("february", 2),
            ("march", 3),
            ("april", 4),
            ("may", 5),
            ("june", 6),
            ("july", 7),
            ("august", 8),
            ("september", 9),
            ("october", 10),
            ("november", 11),
            ("december", 12),
        )
        lowered = text.lower()
        for label, month in month_labels:
            if label in lowered:
                return year, month
        return None

    def _parse_month_panel_year(self, header_text: str | None) -> int | None:
        text = str(header_text or "").strip()
        if not text:
            return None
        normalized = re.sub(r"[<>\u00ab\u00bb\u300a\u300b\s\u5e74]+", "", text)
        if not re.fullmatch(r"20\d{2}", normalized):
            return None
        return int(normalized)

    async def _current_popup_header_text(self, page: Any) -> str | None:
        panel = await self._find_date_panel(page)
        containers = [panel] if panel is not None else [page]
        selectors = (
            ".arco-picker-header",
            ".ant-picker-header",
            '[class*="picker-header"]',
            '[class*="calendar-header"]',
            '[class*="header"]',
        )
        for container in containers:
            for selector in selectors:
                try:
                    locator = container.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=500):
                        text_content = await locator.text_content()
                        if text_content and text_content.strip():
                            return text_content
                except Exception:
                    continue
        return None

    async def _wait_calendar_header_changed(
        self,
        page: Any,
        previous_header: str | None,
        *,
        timeout_ms: int = 1500,
        poll_ms: int = 150,
    ) -> str | None:
        previous = str(previous_header or "").strip()
        waited = 0
        while waited <= timeout_ms:
            current = await self._current_popup_header_text(page)
            if str(current or "").strip() and str(current or "").strip() != previous:
                return current
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None

    async def _click_popup_nav_button_from_selectors(
        self,
        page: Any,
        selector_groups: tuple[str, ...],
    ) -> bool:
        panel = await self._find_date_panel(page)
        containers = [panel] if panel is not None else [page]
        for container in containers:
            for selector in selector_groups:
                try:
                    locator = container.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=500):
                        await locator.click(timeout=5000)
                        if hasattr(page, "wait_for_timeout"):
                            await page.wait_for_timeout(250)
                        return True
                except Exception:
                    continue
        return False

    async def _click_popup_month_nav_button(self, page: Any, direction: str) -> bool:
        selector_map = {
            "prev": (
                'button[aria-label*="previous month"]',
                '.arco-picker-header-prev-btn:not([class*="super"])',
                '.ant-picker-header-prev-btn:not([class*="super"])',
                '[class*="prev-btn"]:not([class*="super"])',
                '[class*="prev"]:not([class*="super"])',
            ),
            "next": (
                'button[aria-label*="next month"]',
                '.arco-picker-header-next-btn:not([class*="super"])',
                '.ant-picker-header-next-btn:not([class*="super"])',
                '[class*="next-btn"]:not([class*="super"])',
                '[class*="next"]:not([class*="super"])',
            ),
        }
        if await self._click_popup_nav_button_from_selectors(page, selector_map.get(direction, ())):
            return True

        text_map = {
            "prev": ("<", "\u2039", "\u3008"),
            "next": (">", "\u203a", "\u3009"),
        }
        panel = await self._find_date_panel(page)
        containers = [panel, page] if panel is not None else [page]
        for container in containers:
            if container is None:
                continue
            for label in text_map.get(direction, ()):
                try:
                    locator = await self._pick_visible_locator(container.get_by_text(label, exact=True))
                    if locator is None:
                        continue
                    await locator.click(timeout=5000)
                    if hasattr(page, "wait_for_timeout"):
                        await page.wait_for_timeout(250)
                    return True
                except Exception:
                    continue
        return False

    async def _navigate_calendar_panel_to_month(self, page: Any, target_year: int, target_month: int) -> bool:
        header_text = await self._current_popup_header_text(page)
        for _ in range(24):
            current = self._parse_calendar_header_month_year_zh(header_text)
            if current == (target_year, target_month):
                return True

            if current is not None:
                current_year, current_month = current
                direction = (
                    "next"
                    if self._calendar_month_key(current_year, current_month)
                    < self._calendar_month_key(target_year, target_month)
                    else "prev"
                )
            else:
                direction = "prev"
            if not await self._click_popup_month_nav_button(page, direction):
                return False
            updated_header = await self._wait_calendar_header_changed(page, header_text)
            if updated_header is None:
                return False
            header_text = updated_header
        return self._parse_calendar_header_month_year_zh(header_text) == (target_year, target_month)

    async def _navigate_month_panel_to_year(self, page: Any, target_year: int) -> bool:
        header_text = await self._current_month_panel_year_text(page)
        for _ in range(8):
            current_year = self._parse_month_panel_year(header_text)
            if current_year == target_year:
                return True
            direction = "next" if current_year is not None and current_year < target_year else "prev"
            if not await self._click_month_panel_year_nav_button(page, direction):
                return False
            updated_header = await self._wait_month_panel_year_changed(page, header_text)
            if updated_header is None:
                return False
            header_text = updated_header
        return self._parse_month_panel_year(header_text) == target_year

    async def _wait_custom_date_selection_applied(
        self,
        page: Any,
        *,
        granularity: str,
        start_date: str | None,
        end_date: str | None,
        timeout_ms: int = 2500,
        poll_ms: int = 250,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            state = await self._current_selection_state(page)
            if self._selection_state_matches_target(
                state,
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            ):
                return True
            summary = state.get("raw_text") if state else await self._current_date_summary_text(page)
            if self._custom_date_summary_matches(
                summary,
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            ):
                return True
            trigger_text = await self._current_date_trigger_text(page)
            if trigger_text and trigger_text != summary and self._custom_date_summary_matches(
                trigger_text,
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            ):
                return True
            if await self._selection_hints_visible(
                page,
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            ):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _wait_date_selection_applied(
        self,
        page: Any,
        target_label: str,
        *,
        timeout_ms: int = 2500,
        poll_ms: int = 250,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            current_label = await self._current_date_label(page)
            if current_label == target_label:
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _select_single_day_value(self, page: Any, iso_date: str) -> bool:
        try:
            target_date = datetime.strptime(str(iso_date), "%Y-%m-%d")
        except ValueError:
            return False
        if not await self._navigate_calendar_panel_to_month(page, target_date.year, target_date.month):
            return False
        return await self._select_calendar_day(page, target_date.day)

    async def _select_calendar_day(self, page: Any, day: int) -> bool:
        day_candidates = (str(day), f"{day:02d}")
        panel = await self._find_date_panel(page)
        containers = [panel] if panel is not None else [page]
        in_view_selectors = (
            ".arco-picker-cell-in-view",
            ".ant-picker-cell-in-view",
            '[class*="cell-in-view"]',
            '[class*="in-view"]',
        )
        for container in containers:
            if container is None:
                continue
            for candidate in day_candidates:
                for in_view_selector in in_view_selectors:
                    try:
                        in_view_scope = container.locator(in_view_selector)
                        matches = in_view_scope.get_by_text(candidate, exact=True)
                        locator = await self._pick_visible_locator(matches, timeout_ms=1000)
                        if locator is not None:
                            await locator.click(timeout=5000)
                            if hasattr(page, "wait_for_timeout"):
                                await page.wait_for_timeout(300)
                            return True
                    except Exception:
                        continue
                try:
                    matches = container.get_by_text(candidate, exact=True)
                    locator = await self._pick_visible_locator(matches, timeout_ms=1000)
                    if locator is not None:
                        await locator.click(timeout=5000)
                        if hasattr(page, "wait_for_timeout"):
                            await page.wait_for_timeout(300)
                        return True
                except Exception:
                    continue
        return False

    async def _select_week_range_value(self, page: Any, start_date: str, end_date: str) -> bool:
        try:
            start_value = datetime.strptime(str(start_date), "%Y-%m-%d")
        except ValueError:
            return False
        if not await self._navigate_calendar_panel_to_month(page, start_value.year, start_value.month):
            return False
        return await self._select_calendar_day(page, start_value.day)

    async def _select_month_value(self, page: Any, iso_date: str) -> bool:
        try:
            target_date = datetime.strptime(str(iso_date), "%Y-%m-%d")
        except ValueError:
            return False

        if not await self._navigate_month_panel_to_year(page, target_date.year):
            return False

        month_labels = self._month_leaf_labels(iso_date)
        if not month_labels:
            return False
        locator = await self._find_month_grid_cell(page, month_labels[0])
        if locator is None:
            return False
        try:
            await locator.hover(timeout=5000)
        except Exception:
            pass
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(150)
        await locator.click(timeout=5000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(300)
        return True

    def _resolve_option_from_context(self) -> DateOption:
        config = self.ctx.config or {}
        time_selection = config.get("time_selection") if isinstance(config.get("time_selection"), dict) else {}
        if str(time_selection.get("mode") or "").strip().lower() == "preset":
            raw = str(time_selection.get("preset") or "").strip().lower()
        else:
            raw = str(
                config.get("date_preset")
                or config.get("preset")
                or config.get("granularity")
                or "daily"
            ).strip().lower()

        if raw in {"today", "today_realtime"}:
            return DateOption.TODAY_REALTIME
        if raw in {"yesterday"}:
            return DateOption.YESTERDAY
        if raw in {"weekly", "week", "w", "last_7_days"}:
            return DateOption.LAST_7_DAYS
        if raw in {"monthly", "month", "m", "last_30_days"}:
            return DateOption.LAST_30_DAYS
        if raw in {"daily", "day", "d"}:
            return DateOption.YESTERDAY
        return DateOption.YESTERDAY

    def _target_date_label(self, config: dict[str, Any]) -> str:
        domain = str((self.ctx.config or {}).get("data_domain") or self.data_domain or "products").strip().lower()
        time_selection = config.get("time_selection")
        if isinstance(time_selection, dict):
            if str(time_selection.get("mode") or "").strip().lower() == "preset" and time_selection.get("preset"):
                preset_value = str(time_selection["preset"])
                if domain == "services" and str(preset_value).strip().lower() == "today_realtime":
                    raise ValueError("unsupported preset 'today_realtime' for shopee/services")
                normalized = normalize_time_request(
                    domain,
                    time_mode="preset",
                    value=preset_value,
                )
                return preset_label(normalized["value"])

        if config.get("date_preset"):
            preset_value = str(config["date_preset"])
            if domain == "services" and preset_value.strip().lower() == "today_realtime":
                raise ValueError("unsupported preset 'today_realtime' for shopee/services")
            normalized = normalize_time_request(
                domain,
                time_mode="preset",
                value=preset_value,
            )
            return preset_label(normalized["value"])

        if "preset" in config:
            preset_value = str(config["preset"])
            if domain == "services" and preset_value.strip().lower() == "today_realtime":
                raise ValueError("unsupported preset 'today_realtime' for shopee/services")
            normalized = normalize_time_request(
                domain,
                time_mode="preset",
                value=preset_value,
            )
            return preset_label(normalized["value"])

        granularity = str(config.get("granularity") or "daily").strip().lower()
        preset_by_granularity = {
            "day": "yesterday",
            "daily": "yesterday",
            "d": "yesterday",
            "week": "last_7_days",
            "weekly": "last_7_days",
            "w": "last_7_days",
            "month": "last_30_days",
            "monthly": "last_30_days",
            "m": "last_30_days",
        }
        preset_value = preset_by_granularity.get(granularity)
        if preset_value:
            return preset_label(preset_value)
        normalized = normalize_time_request(
            domain,
            time_mode="granularity",
            value=granularity,
        )
        return granularity_label(normalized["value"])

    async def _run_custom_selection(self, page: Any) -> None:
        config = self.ctx.config or {}
        target = self._resolve_custom_target(config)
        granularity = self._normalize_custom_granularity(target["granularity"])
        start_date = target["start_date"]
        end_date = target["end_date"]

        current_summary = await self._current_date_summary_text(page)
        if self._custom_date_summary_matches(
            current_summary,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
        ):
            return

        await self._open_date_picker(page)

        if granularity == "daily":
            if not await self._hover_text_option(page, "按日"):
                raise RuntimeError("date option was not clicked")
            if not target["target_iso_date"] or not await self._select_single_day_value(page, target["target_iso_date"]):
                raise RuntimeError("date option was not clicked")
            if not await self._wait_custom_date_selection_applied(
                page,
                granularity="daily",
                start_date=start_date,
                end_date=end_date,
            ):
                raise RuntimeError("date selection did not apply")
            return

        if granularity == "weekly":
            if not await self._hover_text_option(page, "按周"):
                raise RuntimeError("date option was not clicked")
            if not start_date or not end_date or not await self._select_week_range_value(page, start_date, end_date):
                raise RuntimeError("date option was not clicked")
            if not await self._wait_custom_date_selection_applied(
                page,
                granularity="weekly",
                start_date=start_date,
                end_date=end_date,
            ):
                raise RuntimeError("date selection did not apply")
            return

        if granularity == "monthly":
            if not await self._hover_text_option(page, "按月"):
                raise RuntimeError("date option was not clicked")
            if not target["target_iso_date"] or not await self._select_month_value(page, target["target_iso_date"]):
                raise RuntimeError("date option was not clicked")
            if not await self._wait_custom_date_selection_applied(
                page,
                granularity="monthly",
                start_date=start_date,
                end_date=end_date,
            ):
                raise RuntimeError("date selection did not apply")
            return

        raise RuntimeError("unsupported custom date granularity")

    async def _run_preset_selection(self, page: Any) -> None:
        config = self.ctx.config or {}
        target_text = self._target_date_label(config)
        current_label = await self._current_date_label(page)
        if current_label == target_text:
            return

        await self._open_date_picker(page)
        if target_text == self.sel.preset_labels.get("yesterday"):
            direct_clicked = await self._click_text_option(page, target_text)
            if direct_clicked:
                applied = await self._wait_date_selection_applied(page, target_text)
                if not applied:
                    raise RuntimeError("date selection did not apply")
                return

            day_mode_clicked = await self._hover_text_option(page, "按日")
            if not day_mode_clicked:
                raise RuntimeError("date option was not clicked")
            single_day_target = self._single_day_target_value(config)
            if single_day_target:
                selected = await self._select_single_day_value(page, single_day_target)
                if not selected:
                    raise RuntimeError("date option was not clicked")
                applied = await self._wait_date_selection_applied(page, target_text)
                if not applied:
                    raise RuntimeError("date selection did not apply")
            return

        clicked = await self._click_text_option(page, target_text)
        if not clicked:
            raise RuntimeError("date option was not clicked")
        applied = await self._wait_date_selection_applied(page, target_text)
        if not applied:
            raise RuntimeError("date selection did not apply")

    async def run(self, page: Any, option: DateOption | None = None) -> DatePickResult:  # type: ignore[override]
        resolved_option = option or self._resolve_option_from_context()
        try:
            custom_selection = self._custom_time_selection(self.ctx.config or {})
            if custom_selection is not None:
                await self._run_custom_selection(page)
            else:
                await self._run_preset_selection(page)
            return DatePickResult(success=True, message="ok", option=resolved_option)
        except Exception as exc:
            return DatePickResult(success=False, message=str(exc), option=resolved_option)
