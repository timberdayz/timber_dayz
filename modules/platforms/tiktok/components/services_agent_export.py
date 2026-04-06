from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
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
        if self.ctx.config is None:
            self.ctx.config = {}
        params = dict((self.ctx.config or {}).get("params") or {})
        params.setdefault("sub_domain", "agent")
        self.ctx.config["sub_domain"] = "agent"
        self.ctx.config["params"] = params

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

    async def _export_button_locator(self, page: Any) -> Any | None:
        helper = TiktokExport(self.ctx)
        for selector in helper._export_button_selectors():
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

    async def _no_exportable_data(self, page: Any) -> bool:
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
            text = str(value or "").strip().lower()
            if not text:
                continue
            if attr == "class" and "disabled" in text:
                return True
            if text in {"true", "disabled"}:
                return True
        return False

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        entry_state = await self._wait_for_entry_state(page)
        current_url = str(getattr(page, "url", "") or "")

        if entry_state == "login":
            return ExportResult(success=False, message="login required before services agent export", file_path=None)

        region = self._target_region() or self._target_region_from_page_url(current_url)

        if entry_state != "services":
            target_url = self._services_page_url(region) if region else self._generic_services_page_url()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(800)
            current_url = str(getattr(page, "url", "") or "")
            region = region or self._target_region_from_page_url(current_url)

        if self._is_login_page(current_url):
            return ExportResult(success=False, message="login required before services agent export", file_path=None)

        if region:
            self.ctx.config["shop_region"] = region
            switch_result = await self._run_shop_switch(page)
            if not getattr(switch_result, "success", False):
                return ExportResult(
                    success=False,
                    message=getattr(switch_result, "message", "shop switch failed"),
                    file_path=None,
                )

        date_option = self._date_option_from_context()
        if date_option is not None:
            if not await self._date_selection_already_satisfied(page, date_option):
                date_result = await self._run_date_picker(page, date_option)
                if not getattr(date_result, "success", False):
                    return ExportResult(
                        success=False,
                        message=getattr(date_result, "message", "date picker failed"),
                        file_path=None,
                    )
                if not await self._confirm_date_selection(page, date_option):
                    return ExportResult(success=False, message="date state not confirmed", file_path=None)

        if await self._no_exportable_data(page):
            return ExportResult(
                success=True,
                message="no exportable agent service data for selected range",
                file_path=None,
            )

        export_result = await self._run_export(page)
        if not getattr(export_result, "success", False):
            return ExportResult(
                success=False,
                message=getattr(export_result, "message", "services agent export failed"),
                file_path=None,
            )

        file_path = getattr(export_result, "file_path", None)
        if not file_path:
            return ExportResult(success=False, message="services agent export did not produce file_path", file_path=None)

        return ExportResult(success=True, message=getattr(export_result, "message", "ok"), file_path=file_path)
