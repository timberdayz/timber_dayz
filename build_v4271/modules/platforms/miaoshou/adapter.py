from __future__ import annotations

"""Miaoshou ERP platform adapter (skeleton).

This adapter provides component factories for Miaoshou ERP platform.
No side effects on import.
"""
from modules.platforms.adapter_base import PlatformAdapter
from modules.platforms.miaoshou.components.login import MiaoshouLogin


class MiaoshouAdapter(PlatformAdapter):
    platform_id: str = "miaoshou"

    def login(self) -> MiaoshouLogin:  # type: ignore[override]
        return MiaoshouLogin(self.ctx)

    def navigation(self):  # type: ignore[override]
        raise NotImplementedError("miaoshou/navigation is no longer a default adapter surface in V2")

    def date_picker(self):  # type: ignore[override]
        raise NotImplementedError("miaoshou/date_picker is no longer a default adapter surface in V2")

    def exporter(self):  # type: ignore[override]
        raise NotImplementedError("miaoshou/export is no longer a default adapter surface in V2")

    def capabilities(self) -> dict[str, dict[str, bool]]:  # type: ignore[override]
        return {
            "products": {"date_picker": False, "export": False, "metrics": False},
            "orders": {"date_picker": False, "export": False, "metrics": False},
            "analytics": {"date_picker": False, "export": False, "metrics": False},
            "finance": {"date_picker": False, "export": False, "metrics": False},
        }
