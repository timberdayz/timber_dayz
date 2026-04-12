from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportMode, ExportResult
from modules.platforms.shopee.components import _download_helpers as download_helpers
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.services_config import ServicesSelectors
from modules.platforms.shopee.components.services_export_base import ShopeeServicesExportBase


class ShopeeServicesAiAssistantExport(ShopeeServicesExportBase):
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
        super().__init__(ctx, selectors=selectors, service_selectors=service_selectors)

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
            await self._ensure_products_page_ready(page)
            await self._ensure_shop_selected(page)
            await self._ensure_date_selection(page)

            trigger_button = await self.trigger_export(page)
            file_path = await self.collect_download_result(page, trigger_button)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            if await self._detect_export_throttled(page):
                return ExportResult(success=False, message="export throttled", file_path=None)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
