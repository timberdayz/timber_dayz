from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from modules.components.base import ComponentBase, ResultBase


class TargetPage(str, Enum):
    PRODUCTS_PERFORMANCE = "products_performance"
    TRAFFIC_OVERVIEW = "traffic_overview"
    SERVICE_ANALYTICS = "service_analytics"
    ORDERS = "orders"
    FINANCE = "finance"
    WAREHOUSE_CHECKLIST = "warehouse_checklist"


@dataclass
class NavigationResult(ResultBase):
    url: str = ""


class NavigationComponent(ComponentBase):
    def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        raise NotImplementedError

