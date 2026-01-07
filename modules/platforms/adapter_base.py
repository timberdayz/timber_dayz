"""Platform adapter base interface.

Adapters declare the available components for a given platform and provide
factory methods to instantiate them.
"""
from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent
from modules.components.navigation.base import NavigationComponent
from modules.components.date_picker.base import DatePickerComponent
from modules.components.export.base import ExportComponent


class PlatformAdapter:
    platform_id: str = "generic"

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx

    # Factories — concrete adapters should override
    def login(self) -> LoginComponent:
        raise NotImplementedError

    def navigation(self) -> NavigationComponent:
        raise NotImplementedError

    def date_picker(self) -> DatePickerComponent:
        raise NotImplementedError

    def exporter(self) -> ExportComponent:
        raise NotImplementedError

    # Capability map (optional extension point)
    def capabilities(self) -> dict[str, Any]:
        return {
            "products": {"date_picker": True, "export": True},
            "analytics": {"date_picker": True, "export": True},
            "orders": {"date_picker": False, "export": True},
            "finance": {"date_picker": False, "export": True},
        }

