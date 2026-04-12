from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportMode, ExportResult
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.services_config import ServicesSelectors
from modules.platforms.shopee.components.services_export_base import ShopeeServicesExportBase


class ShopeeServicesAgentExport(ShopeeServicesExportBase):
    platform = "shopee"
    component_type = "export"
    data_domain = "services"
    sub_domain = "agent"
    DOWNLOAD_MODE = "task_row"

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: ProductsSelectors | None = None,
        service_selectors: ServicesSelectors | None = None,
    ) -> None:
        super().__init__(ctx, selectors=selectors, service_selectors=service_selectors)

    async def _wait_download_complete(self, page):  # type: ignore[override]
        return await super()._wait_download_complete(page)

    async def ensure_page_ready(self, page: Any) -> None:
        await self._ensure_products_page_ready(page)

    async def ensure_shop_ready(self, page: Any) -> None:
        await self._ensure_shop_selected(page)

    async def ensure_date_ready(self, page: Any) -> None:
        picker = ShopeeDatePicker(self.ctx)
        result = await picker.run(page, picker._resolve_option_from_context())
        if not getattr(result, "success", False):
            raise RuntimeError(getattr(result, "message", "date picker failed"))

    async def trigger_export(self, page: Any) -> Any:
        await self._trigger_export(page)
        return True

    async def collect_download_result(self, page: Any, _trigger_state: Any) -> str | None:
        return await self._wait_download_complete(page)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self.ensure_page_ready(page)
            await self.ensure_shop_ready(page)
            await self.ensure_date_ready(page)

            await self.trigger_export(page)
            post_action_state = await self._wait_export_post_action_state(page)
            if post_action_state in {"download_started", "report_progress"}:
                throttled = False
            elif post_action_state == "throttled":
                throttled = True
            else:
                throttled = await self._detect_export_throttled(page)

            if throttled:
                retry_ready = await self._wait_export_retry_ready(page)
                if not retry_ready:
                    return ExportResult(success=False, message="export throttled and retry not ready", file_path=None)
                await self.trigger_export(page)
                retry_post_action_state = await self._wait_export_post_action_state(page)
                if retry_post_action_state in {"download_started", "report_progress"}:
                    throttled = False
                elif retry_post_action_state == "throttled":
                    throttled = True
                else:
                    throttled = await self._detect_export_throttled(page)
                if throttled:
                    await self._cancel_download_waiter()
                    return ExportResult(success=False, message="export throttled and retry not ready", file_path=None)

            file_path = await self.collect_download_result(page, True)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
