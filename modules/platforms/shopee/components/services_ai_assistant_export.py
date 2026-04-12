from __future__ import annotations

from dataclasses import replace
from typing import Any

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.shopee.components import _download_helpers as download_helpers
from modules.platforms.shopee.components.business_analysis_common import (
    granularity_label,
    normalize_time_request,
    preset_label,
)
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_config import ServicesSelectors


class ShopeeServicesAiAssistantExport(ExportComponent):
    platform = "shopee"
    component_type = "export"
    data_domain = "services"
    sub_domain = "ai_assistant"
    DOWNLOAD_MODE = "direct"
    DIRECT_DOWNLOAD_EVENT_TIMEOUT_MS = 10000

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: ProductsSelectors | None = None,
        service_selectors: ServicesSelectors | None = None,
    ) -> None:
        super().__init__(ctx)
        self.service_sel = service_selectors or ServicesSelectors()
        self.sel = (
            selectors
            or replace(
                ProductsSelectors(),
                overview_path=self.service_sel.service_paths["ai_assistant"],
            )
        )
        self._shared = ShopeeProductsExport(ctx, selectors=self.sel)
        self._shared._target_date_label = self._target_date_label  # type: ignore[method-assign]

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return self.service_sel.service_paths["ai_assistant"] in current

    def _validate_services_preset(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "today_realtime":
            raise ValueError("unsupported preset 'today_realtime' for shopee/services")
        return normalized

    async def _ensure_products_page_ready(self, page: Any) -> None:
        if self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            return
        target_url = f"https://seller.shopee.cn{self.service_sel.service_paths['ai_assistant']}"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(1200)
        if not self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            raise RuntimeError("services page is not ready")

    def _target_date_label(self, config: dict[str, Any]) -> str:
        time_selection = config.get("time_selection")
        if isinstance(time_selection, dict):
            if str(time_selection.get("mode") or "").strip().lower() == "preset" and time_selection.get("preset"):
                normalized = normalize_time_request(
                    "services",
                    time_mode="preset",
                    value=self._validate_services_preset(str(time_selection["preset"])),
                )
                return preset_label(normalized["value"])

        if config.get("date_preset"):
            normalized = normalize_time_request(
                "services",
                time_mode="preset",
                value=self._validate_services_preset(str(config["date_preset"])),
            )
            return preset_label(normalized["value"])

        if "preset" in config:
            normalized = normalize_time_request(
                "services",
                time_mode="preset",
                value=self._validate_services_preset(str(config["preset"])),
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
            "services",
            time_mode="granularity",
            value=granularity,
        )
        return granularity_label(normalized["value"])

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...]) -> Any | None:
        return await self._shared._first_visible_locator(page, selectors)

    async def _detect_export_throttled(self, page: Any) -> bool:
        return await self._shared._detect_export_throttled(page)

    async def _ensure_shop_selected(self, page: Any) -> None:
        await self._shared._ensure_shop_selected(page)

    async def _ensure_date_selection(self, page: Any) -> None:
        await self._shared._ensure_date_selection(page)

    async def ensure_page_ready(self, page: Any) -> None:
        await self._ensure_products_page_ready(page)

    async def ensure_shop_ready(self, page: Any) -> None:
        await self._ensure_shop_selected(page)

    async def ensure_date_ready(self, page: Any) -> None:
        await self._ensure_date_selection(page)

    async def trigger_export(self, page: Any) -> Any:
        button = await self._first_visible_locator(page, self.sel.export_buttons)
        if button is None:
            raise RuntimeError("export button not found")
        return button

    async def collect_download_result(self, page: Any, trigger_button: Any) -> str | None:
        granularity = str((self.ctx.config or {}).get("granularity") or "manual")
        return await download_helpers.capture_direct_download_artifact(
            page=page,
            click_action=lambda: trigger_button.click(timeout=5000),
            ctx=self.ctx,
            data_type="services",
            granularity=granularity,
            subtype="ai_assistant",
            timeout_ms=self.DIRECT_DOWNLOAD_EVENT_TIMEOUT_MS,
            reconcile_timeout_ms=12000,
            filename_hints=("shop_ai_assistant", "assistant", "chat"),
            suggested_filename="services-ai-assistant-export.xlsx",
        )

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self.ensure_page_ready(page)
            await self.ensure_shop_ready(page)
            await self.ensure_date_ready(page)

            trigger_button = await self.trigger_export(page)
            file_path = await self.collect_download_result(page, trigger_button)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            if await self._detect_export_throttled(page):
                return ExportResult(success=False, message="export throttled", file_path=None)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
