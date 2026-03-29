from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.shopee.components.business_analysis_common import normalize_time_request
from modules.platforms.shopee.components.products_config import ProductsSelectors


class ShopeeProductsExport(ExportComponent):
    platform = "shopee"
    component_type = "export"
    data_domain = "products"

    def __init__(self, ctx: ExecutionContext, selectors: ProductsSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or ProductsSelectors()

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return self.sel.overview_path in current

    def _known_throttled_texts(self) -> tuple[str, ...]:
        return self.sel.throttled_texts

    def _is_export_throttled(self, text: str) -> bool:
        content = str(text or "").strip().lower()
        if not content:
            return False
        return any(token.lower() in content for token in self._known_throttled_texts())

    async def _ensure_products_page_ready(self, page: Any) -> None:
        if self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            return
        raise RuntimeError("products overview page is not ready")

    async def _ensure_shop_selected(self, page: Any) -> None:
        return None

    async def _ensure_date_selection(self, page: Any) -> None:
        config = self.ctx.config or {}
        if "preset" in config:
            normalize_time_request("products", time_mode="preset", value=str(config["preset"]))
            return
        granularity = str(config.get("granularity") or "daily")
        normalize_time_request("products", time_mode="granularity", value=granularity)

    async def _trigger_export(self, page: Any) -> None:
        return None

    async def _detect_export_throttled(self, page: Any) -> bool:
        return False

    async def _wait_export_retry_ready(self, page: Any) -> bool:
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(500)
        return True

    async def _wait_download_complete(self, page: Any) -> str | None:
        return None

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self._ensure_products_page_ready(page)
            await self._ensure_shop_selected(page)
            await self._ensure_date_selection(page)

            await self._trigger_export(page)
            throttled = await self._detect_export_throttled(page)
            if throttled:
                retry_ready = await self._wait_export_retry_ready(page)
                if not retry_ready:
                    return ExportResult(success=False, message="export throttled and retry not ready")
                await self._trigger_export(page)
                throttled = await self._detect_export_throttled(page)
                if throttled:
                    return ExportResult(success=False, message="export throttled and retry not ready")

            file_path = await self._wait_download_complete(page)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
