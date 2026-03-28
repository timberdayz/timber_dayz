from __future__ import annotations

"""Shopee platform adapter (skeleton).

This adapter wires platform-specific component implementations.
No side effects on import.
"""
from modules.components.base import ExecutionContext
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.shopee.components.login import ShopeeLogin
from modules.platforms.shopee.components.metrics_selector import ShopeeMetricsSelector
from modules.platforms.shopee.components.orders_export import ShopeeOrdersExport
from modules.platforms.shopee.components.finance_export import ShopeeFinanceExport
from modules.platforms.shopee.components.services_export import ShopeeServicesExport


class ShopeeAdapter(PlatformAdapter):
    platform_id: str = "shopee"

    def login(self) -> ShopeeLogin:  # type: ignore[override]
        return ShopeeLogin(self.ctx)

    def navigation(self):  # type: ignore[override]
        raise NotImplementedError("shopee/navigation is no longer a default adapter surface in V2")

    def date_picker(self):  # type: ignore[override]
        raise NotImplementedError("shopee/date_picker is no longer a default adapter surface in V2")

    def exporter(self):  # type: ignore[override]
        raise NotImplementedError("shopee/export is no longer a default adapter surface in V2")


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
            "products": {"date_picker": False, "export": False, "metrics": False},
            "analytics": {"date_picker": False, "export": False, "metrics": False},
            "services": {"date_picker": False, "export": False, "metrics": False},
            "orders": {"date_picker": False, "export": False, "metrics": False},
            "finance": {"date_picker": False, "export": False, "metrics": False},
        }
