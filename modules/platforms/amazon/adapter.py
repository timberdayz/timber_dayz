from __future__ import annotations

"""Amazon (Seller Central) platform adapter (skeleton).

No side effects on import. Provides component factories.
"""
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.amazon.components.login import AmazonLogin
from modules.platforms.amazon.components.navigation import AmazonNavigation
from modules.platforms.amazon.components.date_picker import AmazonDatePicker
from modules.platforms.amazon.components.export import AmazonExporterComponent


class AmazonAdapter(PlatformAdapter):
    platform_id: str = "amazon"

    def login(self) -> AmazonLogin:  # type: ignore[override]
        return AmazonLogin(self.ctx)

    def navigation(self) -> AmazonNavigation:  # type: ignore[override]
        return AmazonNavigation(self.ctx)

    def date_picker(self) -> AmazonDatePicker:  # type: ignore[override]
        return AmazonDatePicker(self.ctx)

    def exporter(self) -> AmazonExporterComponent:  # type: ignore[override]
        return AmazonExporterComponent(self.ctx)

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": True, "export": True, "metrics": False},
            "analytics": {"date_picker": True, "export": True, "metrics": False},
            "orders": {"date_picker": True, "export": True, "metrics": False},
            "finance": {"date_picker": False, "export": True, "metrics": False},
            "services": {"date_picker": False, "export": True, "metrics": False},
        }

