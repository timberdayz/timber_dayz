from __future__ import annotations

"""Shopee platform adapter (skeleton).

This adapter wires platform-specific component implementations.
No side effects on import.
"""
from modules.components.base import ExecutionContext
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.shopee.components.login import ShopeeLogin
from modules.platforms.shopee.components.navigation import ShopeeNavigation
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
from modules.platforms.shopee.components.export import ShopeeExporterComponent
from modules.platforms.shopee.components.metrics_selector import ShopeeMetricsSelector
from modules.platforms.shopee.components.orders_export import ShopeeOrdersExport
from modules.platforms.shopee.components.finance_export import ShopeeFinanceExport
from modules.platforms.shopee.components.services_export import ShopeeServicesExport


class ShopeeAdapter(PlatformAdapter):
    platform_id: str = "shopee"

    def login(self) -> ShopeeLogin:  # type: ignore[override]
        return ShopeeLogin(self.ctx)

    def navigation(self) -> ShopeeNavigation:  # type: ignore[override]
        return ShopeeNavigation(self.ctx)

    def date_picker(self) -> ShopeeDatePicker:  # type: ignore[override]
        return ShopeeDatePicker(self.ctx)

    def exporter(self) -> ShopeeExporterComponent:  # type: ignore[override]
        return ShopeeExporterComponent(self.ctx)


    def orders_export(self) -> ShopeeOrdersExport:
        return ShopeeOrdersExport(self.ctx)

    def finance_export(self) -> ShopeeFinanceExport:
        return ShopeeFinanceExport(self.ctx)

    def services_export(self) -> ShopeeServicesExport:
        return ShopeeServicesExport(self.ctx)

    def metrics_selector(self) -> ShopeeMetricsSelector:
        return ShopeeMetricsSelector(self.ctx)

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": True, "export": True, "metrics": True},
            "analytics": {"date_picker": True, "export": True, "metrics": False},
            "services": {"date_picker": False, "export": True, "metrics": False},
            "orders": {"date_picker": False, "export": True, "metrics": False},  # deprecated soon
            "finance": {"date_picker": False, "export": True, "metrics": False},
        }

