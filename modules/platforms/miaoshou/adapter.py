from __future__ import annotations

"""Miaoshou ERP platform adapter (skeleton).

This adapter provides component factories for Miaoshou ERP platform.
No side effects on import.
"""
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.miaoshou.components.login import MiaoshouLogin
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.date_picker import MiaoshouDatePicker
from modules.platforms.miaoshou.components.export import MiaoshouExporterComponent


class MiaoshouAdapter(PlatformAdapter):
    platform_id: str = "miaoshou"

    def login(self) -> MiaoshouLogin:  # type: ignore[override]
        return MiaoshouLogin(self.ctx)

    def navigation(self) -> MiaoshouNavigation:  # type: ignore[override]
        return MiaoshouNavigation(self.ctx)

    def date_picker(self) -> MiaoshouDatePicker:  # type: ignore[override]
        return MiaoshouDatePicker(self.ctx)

    def exporter(self) -> MiaoshouExporterComponent:  # type: ignore[override]
        return MiaoshouExporterComponent(self.ctx)

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": True, "export": True, "metrics": False},
            "orders": {"date_picker": True, "export": True, "metrics": False},
            "analytics": {"date_picker": True, "export": True, "metrics": False},
            "finance": {"date_picker": False, "export": True, "metrics": False},
        }
