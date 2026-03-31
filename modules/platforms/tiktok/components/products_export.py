from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
from modules.platforms.tiktok.components.export import TiktokExport
from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


class TiktokProductsExport(ExportComponent):
    """Canonical TikTok products-domain export entry."""

    platform = "tiktok"
    component_type = "export"
    data_domain = "products"

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _target_region(self) -> str | None:
        config = self.ctx.config or {}
        account = self.ctx.account or {}
        region = str(config.get("shop_region") or account.get("shop_region") or "").strip().upper()
        return region or None

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return "/compass/product-analysis" in current

    def _products_page_url(self, region: str) -> str:
        return f"https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region={region}"

    def _date_option_from_context(self) -> DateOption | None:
        config = self.ctx.config or {}
        params = config.get("params") or {}

        raw = str(
            params.get("date_option")
            or params.get("time_selection")
            or params.get("granularity")
            or config.get("time_selection")
            or config.get("granularity")
            or ""
        ).strip().lower()

        if raw in {"weekly", "last_7_days", "last7days", "last-7-days"}:
            return DateOption.LAST_7_DAYS
        if raw in {"monthly", "last_28_days", "last28days", "last-28-days"}:
            return DateOption.LAST_28_DAYS
        return None

    async def _run_shop_switch(self, page: Any):
        return await TiktokShopSwitch(self.ctx).run(page)

    async def _run_date_picker(self, page: Any, option: DateOption):
        return await TiktokDatePicker(self.ctx).run(page, option)

    async def _run_export(self, page: Any):
        return await TiktokExport(self.ctx).run(page, mode=ExportMode.STANDARD)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        region = self._target_region()
        if not region:
            return ExportResult(success=False, message="shop_region is required", file_path=None)

        current_url = str(getattr(page, "url", "") or "")
        if not self._products_page_looks_ready(current_url):
            await page.goto(self._products_page_url(region), wait_until="domcontentloaded", timeout=60000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(800)

        switch_result = await self._run_shop_switch(page)
        if not getattr(switch_result, "success", False):
            return ExportResult(
                success=False,
                message=getattr(switch_result, "message", "shop switch failed"),
                file_path=None,
            )

        date_option = self._date_option_from_context()
        if date_option is not None:
            date_result = await self._run_date_picker(page, date_option)
            if not getattr(date_result, "success", False):
                return ExportResult(
                    success=False,
                    message=getattr(date_result, "message", "date picker failed"),
                    file_path=None,
                )

        export_result = await self._run_export(page)
        if not getattr(export_result, "success", False):
            return ExportResult(
                success=False,
                message=getattr(export_result, "message", "products export failed"),
                file_path=None,
            )

        file_path = getattr(export_result, "file_path", None)
        if not file_path:
            return ExportResult(success=False, message="products export did not produce file_path", file_path=None)

        return ExportResult(success=True, message=getattr(export_result, "message", "ok"), file_path=file_path)
