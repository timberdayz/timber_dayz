from __future__ import annotations

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.services_config import ServicesSelectors
from modules.platforms.shopee.components.services_export_base import ShopeeServicesExportBase


class ShopeeServicesAiAssistantExport(ShopeeServicesExportBase):
    platform = "shopee"
    component_type = "export"
    data_domain = "services"
    sub_domain = "ai_assistant"

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: ProductsSelectors | None = None,
        service_selectors: ServicesSelectors | None = None,
    ) -> None:
        super().__init__(ctx, selectors=selectors, service_selectors=service_selectors)
