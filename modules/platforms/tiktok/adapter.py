from __future__ import annotations

"""TikTok Shop platform adapter (skeleton).

This adapter provides component factories for TikTok Shop platform.
No side effects on import.
"""
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.tiktok.components.login import TiktokLogin
from modules.platforms.tiktok.components.navigation import TiktokNavigation
from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
from modules.platforms.tiktok.components.export import TiktokExporterComponent
from modules.platforms.tiktok.components.shop_selector import TiktokShopSelector


class TiktokAdapter(PlatformAdapter):
    platform_id: str = "tiktok"

    def login(self) -> TiktokLogin:  # type: ignore[override]
        return TiktokLogin(self.ctx)

    def navigation(self) -> TiktokNavigation:  # type: ignore[override]
        return TiktokNavigation(self.ctx)

    def date_picker(self) -> TiktokDatePicker:  # type: ignore[override]
        return TiktokDatePicker(self.ctx)

    def exporter(self) -> TiktokExporterComponent:  # type: ignore[override]
        return TiktokExporterComponent(self.ctx)

    def shop_selector(self) -> TiktokShopSelector:
        return TiktokShopSelector(self.ctx)

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": True, "export": True, "metrics": True},
            "analytics": {"date_picker": True, "export": True, "metrics": False},
            "orders": {"date_picker": True, "export": True, "metrics": False},
            "finance": {"date_picker": False, "export": True, "metrics": False},
        }
