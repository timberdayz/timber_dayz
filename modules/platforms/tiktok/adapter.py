from __future__ import annotations

"""TikTok Shop platform adapter (skeleton).

This adapter provides component factories for TikTok Shop platform.
No side effects on import.
"""
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.tiktok.components.login import TiktokLogin


class TiktokAdapter(PlatformAdapter):
    platform_id: str = "tiktok"

    def login(self) -> TiktokLogin:  # type: ignore[override]
        return TiktokLogin(self.ctx)

    def navigation(self):  # type: ignore[override]
        raise NotImplementedError("tiktok/navigation is no longer a default adapter surface in V2")

    def date_picker(self):  # type: ignore[override]
        raise NotImplementedError("tiktok/date_picker is no longer a default adapter surface in V2")

    def exporter(self):  # type: ignore[override]
        raise NotImplementedError("tiktok/export is no longer a default adapter surface in V2")

    def shop_switch(self):
        raise NotImplementedError("tiktok/shop_switch is no longer a default adapter surface in V2")

    def shop_selector(self):
        raise NotImplementedError("tiktok/shop_selector is no longer a default adapter surface in V2")

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": False, "export": False, "metrics": False},
            "analytics": {"date_picker": False, "export": False, "metrics": False},
            "orders": {"date_picker": False, "export": False, "metrics": False},
            "finance": {"date_picker": False, "export": False, "metrics": False},
        }
