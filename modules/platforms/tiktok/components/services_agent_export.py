from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from modules.components.base import ExecutionContext
from modules.components.export.base import build_standard_output_root
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.tiktok.components._navigation import goto_when_ready, wait_until_page_settles
from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
from modules.platforms.tiktok.components._download_helpers import (
    cleanup_download_capture,
    create_download_capture,
    resolve_export_timeout_ms,
    save_download_to_target,
)
from modules.platforms.tiktok.components.export import TiktokExport
from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


class TiktokServicesAgentExport(ExportComponent):
    """Canonical TikTok services-agent export entry."""

    platform = "tiktok"
    component_type = "export"
    data_domain = "services"
    sub_domain = "agent"

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)
        self._runtime_logger = getattr(ctx, "logger", None)
        if self.ctx.config is None:
            self.ctx.config = {}
        params = dict((self.ctx.config or {}).get("params") or {})
        params.setdefault("sub_domain", "agent")
        self.ctx.config["sub_domain"] = "agent"
        self.ctx.config["params"] = params
        self._download_capture = None

    def _log_info(self, message: str, *args) -> None:
        if self._runtime_logger is None:
            return
        try:
            self._runtime_logger.info(message, *args)
        except Exception:
            pass

    def _target_region(self) -> str | None:
        config = self.ctx.config or {}
        account = self.ctx.account or {}
        region = str(config.get("shop_region") or account.get("shop_region") or "").strip().upper()
        return region or None

    def _target_region_from_page_url(self, url: str) -> str | None:
        try:
            query = dict(parse_qsl(urlsplit(str(url or "")).query))
            region = str(query.get("shop_region") or "").strip().upper()
            return region or None
        except Exception:
            return None

    def _services_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        return bool(current and "/compass/service-analytics" in current)

    def _is_homepage(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        return bool(current and "/homepage" in current)

    def _is_login_page(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        return bool(current and "/account/login" in current)

    async def _locator_is_visible(self, locator: Any, timeout: int = 500) -> bool:
        try:
            return bool(await locator.is_visible(timeout=timeout))
        except Exception:
            return False

    async def _login_surface_looks_ready(self, page: Any) -> bool:
        probes = (
            page.locator("input[type='password']").first,
            page.locator("input[type='tel']").first,
            page.locator("input[type='email']").first,
            page.locator("input[placeholder*='鎵嬫満鍙?']").first,
            page.locator("input[placeholder*='閭']").first,
        )
        for probe in probes:
            if await self._locator_is_visible(probe, timeout=300):
                return True
        return False

    def _services_page_url(self, region: str) -> str:
        return f"https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region={region}"

    def _generic_services_page_url(self) -> str:
        return "https://seller.tiktokshopglobalselling.com/compass/service-analytics"

    def _homepage_url(self, region: str) -> str:
        return f"https://seller.tiktokshopglobalselling.com/homepage?shop_region={region}"

    def _generic_homepage_url(self) -> str:
        return "https://seller.tiktokshopglobalselling.com/homepage"

    async def _page_body_text(self, page: Any) -> str:
        try:
            body = page.locator("body")
            if hasattr(body, "first"):
                body = body.first
            if hasattr(body, "inner_text"):
                return str(await body.inner_text() or "")
        except Exception:
            pass
        return ""

    async def _is_internal_error_page(self, page: Any) -> bool:
        error_texts = (
            "Seller Condition is undefined",
            "出错了",
            "请重新加载页面",
        )
        for text in error_texts:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await self._locator_is_visible(locator, timeout=200):
                    return True
            except Exception:
                continue

        body_text = await self._page_body_text(page)
        return any(marker in body_text for marker in error_texts)

    def _date_option_from_context(self) -> DateOption | None:
        config = self.ctx.config or {}
        params = config.get("params") or {}
        raw_candidate = (
            params.get("date_option")
            or params.get("date_preset")
            or config.get("date_preset")
            or params.get("granularity")
            or config.get("granularity")
            or ""
        )
        raw = str(raw_candidate or "").strip().lower()

        if raw in {"today", "today_realtime"}:
            return DateOption.TODAY_REALTIME
        if raw in {"yesterday"}:
            return DateOption.YESTERDAY
        if raw in {"weekly", "last_7_days", "last7days", "last-7-days"}:
            return DateOption.LAST_7_DAYS
        if raw in {
            "monthly",
            "last_30_days",
            "last30days",
            "last-30-days",
            "last_28_days",
            "last28days",
            "last-28-days",
        }:
            return DateOption.LAST_30_DAYS
        if raw in {"daily", "day"}:
            return DateOption.YESTERDAY
        return None

    async def _run_shop_switch(self, page: Any):
        return await TiktokShopSwitch(self.ctx).run(page)

    async def _run_date_picker(self, page: Any, option: DateOption):
        return await TiktokDatePicker(self.ctx).run(page, option)

    async def _date_selection_already_satisfied(self, page: Any, option: DateOption) -> bool:
        return await TiktokDatePicker(self.ctx)._current_range_matches(page, option)

    async def _confirm_date_selection(self, page: Any, option: DateOption) -> bool:
        return await TiktokDatePicker(self.ctx)._current_range_matches(page, option)

    async def _run_export(self, page: Any):
        return await TiktokExport(self.ctx).run(page, mode=ExportMode.STANDARD)

    async def _wait_services_page_settled(
        self,
        page: Any,
        *,
        timeout_ms: int = 5000,
        poll_ms: int = 200,
    ) -> str:
        waited = 0
        while waited <= timeout_ms:
            current_url = str(getattr(page, "url", "") or "")
            if self._services_page_looks_ready(current_url):
                return current_url
            if self._is_login_page(current_url):
                return current_url
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return str(getattr(page, "url", "") or "")

    async def ensure_page_ready(self, page: Any) -> str:
        current_url = await wait_until_page_settles(page)
        if self._is_login_page(current_url) and await self._login_surface_looks_ready(page):
            raise RuntimeError("login required before services agent export")
        if self._is_login_page(current_url):
            raise RuntimeError("login required before services agent export")
        return current_url

    async def ensure_shop_ready(self, page: Any, current_url: str) -> str | None:
        region = self._target_region() or self._target_region_from_page_url(current_url)
        if not region:
            return None

        self.ctx.config["shop_region"] = region
        switch_result = await self._run_shop_switch(page)
        if not getattr(switch_result, "success", False):
            raise RuntimeError(getattr(switch_result, "message", "shop switch failed"))
        return region

    async def ensure_services_ready(self, page: Any) -> str:
        current_url = await wait_until_page_settles(page)
        region = self._target_region() or self._target_region_from_page_url(current_url)
        target_url = self._services_page_url(region) if region else self._generic_services_page_url()

        if not self._services_page_looks_ready(current_url):
            current_url = await goto_when_ready(page, target_url, goto_timeout=60000, settle_timeout_ms=6000, poll_ms=200)

        if await self._is_internal_error_page(page):
            self._log_info("services_agent_export detected internal error page on first load, retrying once")
            current_url = await goto_when_ready(page, target_url, goto_timeout=60000, settle_timeout_ms=6000, poll_ms=200)

        if self._is_login_page(current_url):
            raise RuntimeError("login required before services agent export")
        if await self._is_internal_error_page(page):
            raise RuntimeError("services page internal error")
        return current_url

    async def ensure_date_ready(self, page: Any) -> None:
        date_option = self._date_option_from_context()
        if date_option is None:
            return

        if await self._date_selection_already_satisfied(page, date_option):
            return

        date_result = await self._run_date_picker(page, date_option)
        if not getattr(date_result, "success", False):
            raise RuntimeError(getattr(date_result, "message", "date picker failed"))
        if not await self._confirm_date_selection(page, date_option):
            raise RuntimeError("date state not confirmed")

    async def trigger_export(self, page: Any) -> bool:
        self._download_capture = create_download_capture(page)
        locator = await self._export_button_locator(page)
        if locator is None:
            cleanup_download_capture(page, self._download_capture)
            self._download_capture = None
            return False

        try:
            if hasattr(locator, "scroll_into_view_if_needed"):
                await locator.scroll_into_view_if_needed(timeout=500)
        except Exception:
            pass

        try:
            await locator.click(timeout=3000)
        except Exception:
            cleanup_download_capture(page, self._download_capture)
            self._download_capture = None
            return False

        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(500)
        return True

    async def collect_download_result(self, page: Any) -> str | None:
        capture = self._download_capture
        timeout_ms = resolve_export_timeout_ms(self.ctx.config or {})
        download = None

        try:
            if hasattr(page, "wait_for_event"):
                try:
                    download = await page.wait_for_event("download", timeout=timeout_ms)
                except Exception:
                    download = getattr(capture, "latest_download", None)
            else:
                download = getattr(capture, "latest_download", None)
        finally:
            if capture is not None:
                cleanup_download_capture(page, capture)
            self._download_capture = None

        if download is None:
            return None

        cfg = self.ctx.config or {}
        out_root = build_standard_output_root(
            self.ctx,
            data_type="services",
            granularity=str(cfg.get("granularity") or "range").lower(),
            subtype="agent",
        )
        filename = getattr(download, "suggested_filename", None) or "services-agent.xlsx"
        saved = await save_download_to_target(download, Path(out_root) / filename)
        return str(saved) if saved is not None else None

    def _agent_overview_tab_selectors(self) -> tuple[str, ...]:
        return (
            '[role="tab"]:has-text("\u804a\u5929\u6982\u89c8")',
            'button:has-text("\u804a\u5929\u6982\u89c8")',
            'text=\u804a\u5929\u6982\u89c8',
        )

    def _agent_detail_tab_selectors(self) -> tuple[str, ...]:
        return (
            '[role="tab"]:has-text("\u804a\u5929\u8be6\u60c5")',
            'button:has-text("\u804a\u5929\u8be6\u60c5")',
            'text=\u804a\u5929\u8be6\u60c5',
        )

    def _loading_selectors(self) -> tuple[str, ...]:
        return (
            '[data-tid="m4b_loading"]',
            ".theme-arco-spin",
            ".theme-m4b-loading",
        )

    async def _click_first(self, page: Any, selectors: tuple[str, ...], *, timeout: int = 2000) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() <= 0:
                    continue
                if not await locator.is_visible(timeout=300):
                    continue
                try:
                    await locator.scroll_into_view_if_needed(timeout=500)
                except Exception:
                    pass
                await locator.click(timeout=timeout)
                return True
            except Exception:
                continue
        return False

    async def _any_visible(self, page: Any, selectors: tuple[str, ...], *, timeout: int = 300) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() <= 0:
                    continue
                if await locator.is_visible(timeout=timeout):
                    return True
            except Exception:
                continue
        return False

    async def _tab_looks_selected(self, page: Any, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() <= 0:
                    continue
                if not await locator.is_visible(timeout=200):
                    continue

                explicit_false = False
                for attr in ("aria-selected", "data-selected", "class"):
                    try:
                        value = await locator.get_attribute(attr)
                    except Exception:
                        value = None
                    text = str(value or "").strip().lower()
                    if not text:
                        continue
                    if attr == "class" and any(token in text for token in ("active", "selected", "current")):
                        return True
                    if text == "true":
                        return True
                    if attr in {"aria-selected", "data-selected"} and text == "false":
                        explicit_false = True
                if explicit_false:
                    continue
            except Exception:
                continue
        return False

    async def _tab_state_snapshot(self, page: Any, selectors: tuple[str, ...]) -> str:
        snapshots: list[str] = []
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() <= 0:
                    snapshots.append(f"{selector}:missing")
                    continue
                if not await locator.is_visible(timeout=200):
                    snapshots.append(f"{selector}:hidden")
                    continue
                aria_selected = None
                css_class = None
                try:
                    aria_selected = await locator.get_attribute("aria-selected")
                except Exception:
                    aria_selected = None
                try:
                    css_class = await locator.get_attribute("class")
                except Exception:
                    css_class = None
                snapshots.append(
                    f"{selector}:aria-selected={str(aria_selected or '').strip() or '<none>'},"
                    f"class={str(css_class or '').strip() or '<none>'}"
                )
            except Exception as exc:
                snapshots.append(f"{selector}:error={exc}")
        return " | ".join(snapshots)

    async def _wait_tab_area_ready(
        self,
        page: Any,
        *,
        timeout_ms: int = 12000,
        poll_ms: int = 200,
    ) -> bool:
        waited = 0
        overview_selectors = self._agent_overview_tab_selectors()
        detail_selectors = self._agent_detail_tab_selectors()
        while waited <= timeout_ms:
            if await self._any_visible(page, overview_selectors) and await self._any_visible(page, detail_selectors):
                return True
            if await self._any_visible(page, self._loading_selectors(), timeout=150):
                if hasattr(page, "wait_for_timeout"):
                    await page.wait_for_timeout(poll_ms)
                waited += poll_ms
                continue
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _wait_agent_detail_selected(
        self,
        page: Any,
        selectors: tuple[str, ...],
        *,
        timeout_ms: int = 3000,
        poll_ms: int = 200,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            if await self._tab_looks_selected(page, selectors):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _activate_agent_detail_tab(
        self,
        page: Any,
        selectors: tuple[str, ...],
        *,
        max_attempts: int = 3,
    ) -> bool:
        for attempt in range(max_attempts):
            await self._wait_loading_gone(page, timeout_ms=1500, poll_ms=150)

            before_state = await self._tab_state_snapshot(page, selectors)
            self._log_info(
                "services_agent_export detail tab attempt %s/%s before click: %s",
                attempt + 1,
                max_attempts,
                before_state,
            )

            clicked = await self._click_first(page, selectors, timeout=2000)
            self._log_info(
                "services_agent_export detail tab attempt %s/%s click_result=%s",
                attempt + 1,
                max_attempts,
                clicked,
            )
            if not clicked:
                return False

            selected = await self._wait_agent_detail_selected(page, selectors)
            after_state = await self._tab_state_snapshot(page, selectors)
            self._log_info(
                "services_agent_export detail tab attempt %s/%s selected_after_click=%s after click: %s",
                attempt + 1,
                max_attempts,
                selected,
                after_state,
            )
            if selected:
                return True

            if attempt >= max_attempts - 1:
                break

            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(300)

            tab_area_ready = await self._wait_tab_area_ready(page, timeout_ms=1500, poll_ms=150)
            self._log_info(
                "services_agent_export detail tab attempt %s/%s retry_wait_tab_area_ready=%s",
                attempt + 1,
                max_attempts,
                tab_area_ready,
            )
            if not tab_area_ready:
                return False
        return False

    async def _wait_loading_gone(
        self,
        page: Any,
        *,
        timeout_ms: int = 4000,
        poll_ms: int = 200,
    ) -> bool:
        waited = 0
        selectors = self._loading_selectors()
        while waited <= timeout_ms:
            if not await self._any_visible(page, selectors, timeout=150):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _export_button_locator(self, page: Any) -> Any | None:
        selectors = (
            'button:has-text("\u5bfc\u51fa\u6570\u636e")',
            'button:has-text("\u5bfc\u51fa")',
            'button:has-text("Export")',
            '[data-testid*="export"]',
        )
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() <= 0:
                    continue
                if not await locator.is_visible(timeout=300):
                    continue
                return locator
            except Exception:
                continue
        return None

    async def _agent_detail_business_ready(self, page: Any) -> bool:
        export_button = await self._export_button_locator(page)
        if export_button is not None:
            return True

        if await self._any_visible(
            page,
            (
                ".theme-arco-table",
                "table",
                "text=Customer Service",
                "text=\u5ba2\u670d\u8868\u73b0\u8be6\u60c5",
                "text=\u6682\u65e0\u6570\u636e",
            ),
            timeout=150,
        ):
            return True

        return False

    async def _wait_agent_detail_business_ready(
        self,
        page: Any,
        selectors: tuple[str, ...],
        *,
        timeout_ms: int = 15000,
        poll_ms: int = 300,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            selected = await self._tab_looks_selected(page, selectors)
            business_ready = False
            if selected:
                business_ready = await self._agent_detail_business_ready(page)
                if business_ready:
                    return True
                if await self._no_exportable_data(page):
                    return True

            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms

        selected = await self._tab_looks_selected(page, selectors)
        business_ready = selected and await self._agent_detail_business_ready(page)
        empty_state = selected and await self._no_exportable_data(page)
        loading_visible = await self._any_visible(page, self._loading_selectors(), timeout=150)
        export_visible = await self._export_button_locator(page) is not None
        self._log_info(
            "services_agent_export detail business wait timed out: selected=%s business_ready=%s empty_state=%s loading_visible=%s export_visible=%s",
            selected,
            business_ready,
            empty_state,
            loading_visible,
            export_visible,
        )
        return bool(business_ready or empty_state)

    async def _ensure_agent_detail_ready(self, page: Any) -> bool:
        if not await self._wait_tab_area_ready(page):
            return False

        selectors = self._agent_detail_tab_selectors()
        if await self._tab_looks_selected(page, selectors):
            return await self._wait_agent_detail_business_ready(page, selectors)

        if not await self._activate_agent_detail_tab(page, selectors):
            return False

        return await self._wait_agent_detail_business_ready(page, selectors)

    async def _wait_for_entry_state(
        self,
        page: Any,
        *,
        timeout_ms: int = 15000,
        poll_ms: int = 500,
    ) -> str:
        elapsed = 0
        while elapsed <= timeout_ms:
            current_url = str(getattr(page, "url", "") or "")
            if self._services_page_looks_ready(current_url):
                return "services"
            if self._is_homepage(current_url):
                return "homepage"
            if self._is_login_page(current_url) and await self._login_surface_looks_ready(page):
                return "login"
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
        return "unknown"

    async def _no_exportable_data(self, page: Any) -> bool:
        if await self._any_visible(
            page,
            (
                "text=\u6682\u65e0\u6570\u636e",
            ),
            timeout=150,
        ):
            return True

        try:
            body = page.locator("body")
            if hasattr(body, "first"):
                body = body.first
            if hasattr(body, "inner_text"):
                body_text = str(await body.inner_text() or "")
                if "\u6682\u65e0\u6570\u636e" in body_text:
                    return True
        except Exception:
            pass

        locator = await self._export_button_locator(page)
        if locator is None:
            return False

        try:
            if hasattr(locator, "is_enabled"):
                enabled = await locator.is_enabled()
                if enabled is False:
                    return True
        except Exception:
            pass

        for attr in ("disabled", "aria-disabled", "data-disabled", "class"):
            try:
                value = await locator.get_attribute(attr)
            except Exception:
                value = None
            if attr == "disabled" and value is not None:
                return True
            text = str(value or "").strip().lower()
            if not text:
                continue
            if attr == "class" and "disabled" in text:
                return True
            if text in {"true", "disabled"}:
                return True
        return False

    async def _export_button_enabled(self, page: Any) -> bool:
        locator = await self._export_button_locator(page)
        if locator is None:
            return False

        try:
            if hasattr(locator, "is_enabled"):
                enabled = await locator.is_enabled()
                if enabled is not None:
                    return bool(enabled)
        except Exception:
            pass

        for attr in ("disabled", "aria-disabled", "data-disabled", "class"):
            try:
                value = await locator.get_attribute(attr)
            except Exception:
                value = None
            if attr == "disabled" and value is not None:
                return False
            text = str(value or "").strip().lower()
            if attr == "class" and "disabled" in text:
                return False
            if text in {"true", "disabled"}:
                return False
        return True

    async def _wait_export_readiness_state(
        self,
        page: Any,
        *,
        timeout_ms: int = 4000,
        poll_ms: int = 200,
    ) -> str:
        waited = 0
        while waited <= timeout_ms:
            if await self._any_visible(page, self._loading_selectors(), timeout=150):
                if hasattr(page, "wait_for_timeout"):
                    await page.wait_for_timeout(poll_ms)
                waited += poll_ms
                continue
            if await self._no_exportable_data(page):
                return "empty"
            if await self._export_button_enabled(page):
                return "ready"
            if await self._export_button_locator(page) is not None:
                return "disabled"
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return "unknown"

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            current_url = await self.ensure_page_ready(page)
        except RuntimeError as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)

        try:
            current_url = await self.ensure_services_ready(page)
            await self.ensure_shop_ready(page, current_url)
        except RuntimeError as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)

        if not await self._ensure_agent_detail_ready(page):
            return ExportResult(success=False, message="failed to enter services agent detail page", file_path=None)

        try:
            await self.ensure_date_ready(page)
        except RuntimeError as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)

        export_state = await self._wait_export_readiness_state(page)
        if export_state in {"empty", "disabled"}:
            return ExportResult(
                success=True,
                message="no exportable agent service data for selected range",
                file_path=None,
            )

        triggered = await self.trigger_export(page)
        if not triggered:
            if await self._no_exportable_data(page):
                return ExportResult(
                    success=True,
                    message="no exportable agent service data for selected range",
                    file_path=None,
                )
            return ExportResult(
                success=False,
                message="services agent export failed",
                file_path=None,
            )

        file_path = await self.collect_download_result(page)
        if not file_path:
            return ExportResult(success=False, message="services agent export did not produce file_path", file_path=None)

        return ExportResult(success=True, message="ok", file_path=file_path)
