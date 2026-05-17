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
from modules.platforms.tiktok.components._runtime_diagnostics import (
    attach_tiktok_runtime_diagnostics,
    log_tiktok_runtime_diagnostics,
)
from modules.platforms.tiktok.components.export import TiktokExport
from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


class TiktokAnalyticsExport(ExportComponent):
    """Canonical TikTok analytics-domain export entry."""

    platform = "tiktok"
    component_type = "export"
    data_domain = "analytics"

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)
        self._runtime_logger = getattr(ctx, "logger", None)
        self._download_capture = None

    def _log_info(self, message: str, *args: Any) -> None:
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

    def _analytics_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        return bool(current and "/compass/data-overview" in current)

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

    def _analytics_page_url(self, region: str) -> str:
        return f"https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region={region}"

    def _generic_analytics_page_url(self) -> str:
        return "https://seller.tiktokshopglobalselling.com/compass/data-overview"

    def _homepage_url(self, region: str) -> str:
        return f"https://seller.tiktokshopglobalselling.com/homepage?shop_region={region}"

    def _generic_homepage_url(self) -> str:
        return "https://seller.tiktokshopglobalselling.com/homepage"

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
        if raw in {"monthly", "last_30_days", "last30days", "last-30-days", "last_28_days", "last28days", "last-28-days"}:
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

    async def _wait_analytics_page_settled(
        self,
        page: Any,
        *,
        timeout_ms: int = 5000,
        poll_ms: int = 200,
    ) -> str:
        waited = 0
        while waited <= timeout_ms:
            current_url = str(getattr(page, "url", "") or "")
            if self._analytics_page_looks_ready(current_url):
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
            raise RuntimeError("login required before analytics export")
        if self._is_login_page(current_url):
            raise RuntimeError("login required before analytics export")
        return current_url

    async def ensure_shop_ready(self, page: Any, current_url: str) -> str | None:
        region = self._target_region() or self._target_region_from_page_url(current_url)
        if not region:
            return None

        if self.ctx.config is None:
            self.ctx.config = {}
        self.ctx.config["shop_region"] = region
        switch_result = await self._run_shop_switch(page)
        if not getattr(switch_result, "success", False):
            raise RuntimeError(getattr(switch_result, "message", "shop switch failed"))
        return region

    async def ensure_analytics_ready(self, page: Any) -> str:
        current_url = await wait_until_page_settles(page)
        if self._analytics_page_looks_ready(current_url):
            return current_url

        region = self._target_region() or self._target_region_from_page_url(current_url)
        target_url = self._analytics_page_url(region) if region else self._generic_analytics_page_url()
        self._log_info(
            "tiktok_analytics_export navigating from url=%s to target=%s",
            current_url or "UNKNOWN",
            target_url,
        )
        await log_tiktok_runtime_diagnostics(page, self._runtime_logger, label="analytics_before_goto")
        current_url = await goto_when_ready(page, target_url, goto_timeout=60000, settle_timeout_ms=6000, poll_ms=200)
        await log_tiktok_runtime_diagnostics(page, self._runtime_logger, label="analytics_after_goto")
        if self._is_login_page(current_url):
            raise RuntimeError("login required before analytics export")
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
        helper = TiktokExport(self.ctx)
        self._download_capture = create_download_capture(page)
        clicked = await helper._click_first(page, helper._export_button_selectors(), timeout=3000)
        if not clicked:
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
            data_type="analytics",
            granularity=str(cfg.get("granularity") or "range").lower(),
        )
        filename = getattr(download, "suggested_filename", None) or "analytics.xlsx"
        saved = await save_download_to_target(download, Path(out_root) / filename)
        return str(saved) if saved is not None else None

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
            if self._analytics_page_looks_ready(current_url):
                return "analytics"
            if self._is_homepage(current_url):
                return "homepage"
            if self._is_login_page(current_url) and await self._login_surface_looks_ready(page):
                return "login"
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
        return "unknown"

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        attach_tiktok_runtime_diagnostics(page)
        try:
            current_url = await self.ensure_page_ready(page)
            current_url = await self.ensure_analytics_ready(page)
            await self.ensure_shop_ready(page, current_url)
            await self.ensure_date_ready(page)
        except RuntimeError as exc:
            await log_tiktok_runtime_diagnostics(page, self._runtime_logger, label="analytics_runtime_error")
            return ExportResult(success=False, message=str(exc), file_path=None)

        triggered = await self.trigger_export(page)
        if not triggered:
            return ExportResult(success=False, message="analytics export failed", file_path=None)

        file_path = await self.collect_download_result(page)
        if not file_path:
            return ExportResult(success=False, message="analytics export did not produce file_path", file_path=None)

        return ExportResult(success=True, message="ok", file_path=file_path)
