from __future__ import annotations

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.services_config import ServicesSelectors
from modules.platforms.shopee.components.services_export_base import ShopeeServicesExportBase


class ShopeeServicesAgentExport(ShopeeServicesExportBase):
    platform = "shopee"
    component_type = "export"
    data_domain = "services"
    sub_domain = "agent"

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: ProductsSelectors | None = None,
        service_selectors: ServicesSelectors | None = None,
    ) -> None:
        super().__init__(ctx, selectors=selectors, service_selectors=service_selectors)

    async def _wait_download_complete(self, page):  # type: ignore[override]
        button = await self._wait_top_report_download_button(page)
        if button is None:
            return None
        try:
            await button.click(timeout=5000)
        except Exception:
            return None
        return await super()._wait_download_complete(page)
