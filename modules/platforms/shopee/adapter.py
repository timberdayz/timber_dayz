from __future__ import annotations

"""Shopee platform adapter (skeleton).

This adapter wires platform-specific component implementations.
No side effects on import.
"""
from modules.platforms.adapter_base import PlatformAdapter


class ShopeeAdapter(PlatformAdapter):
    platform_id: str = "shopee"

    def login(self):  # type: ignore[override]
        raise NotImplementedError("shopee/login is no longer a default adapter surface in V2")

    def navigation(self):  # type: ignore[override]
        raise NotImplementedError("shopee/navigation is no longer a default adapter surface in V2")

    def date_picker(self):  # type: ignore[override]
        raise NotImplementedError("shopee/date_picker is no longer a default adapter surface in V2")

    def exporter(self):  # type: ignore[override]
        raise NotImplementedError("shopee/export is no longer a default adapter surface in V2")


    def orders_export(self):
        raise NotImplementedError("shopee/orders_export is no longer a default adapter surface in V2")

    def finance_export(self):
        raise NotImplementedError("shopee/finance_export is no longer a default adapter surface in V2")

    def services_export(self):
        raise NotImplementedError("shopee/services_export is no longer a default adapter surface in V2")

    def metrics_selector(self):
        raise NotImplementedError("shopee/metrics_selector is no longer a default adapter surface in V2")

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": False, "export": False, "metrics": False},
            "analytics": {"date_picker": False, "export": False, "metrics": False},
            "services": {"date_picker": False, "export": False, "metrics": False},
            "orders": {"date_picker": False, "export": False, "metrics": False},
            "finance": {"date_picker": False, "export": False, "metrics": False},
        }
