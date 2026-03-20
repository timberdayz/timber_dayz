from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import (
    NavigationComponent,
    NavigationResult,
    TargetPage,
)
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


class MiaoshouNavigation(NavigationComponent):
    """Minimal Miaoshou navigation component kept for compatibility and smoke tests."""

    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: WarehouseSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or WarehouseSelectors()

    def _target_path(self, target: Any) -> str | None:
        key = str(getattr(target, "value", target)).lower()
        mapping = {
            TargetPage.WAREHOUSE_CHECKLIST.value: self.sel.checklist_path,
            TargetPage.ORDERS.value: "/stat/profit_statistics/detail",
            TargetPage.FINANCE.value: "/finance",
            TargetPage.PRODUCTS_PERFORMANCE.value: "/goods/list",
        }
        return mapping.get(key)

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        path = self._target_path(target)
        if not path:
            return NavigationResult(success=False, url="", message=f"unsupported target: {target}")

        url = f"{self.sel.base_url}{path}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(1000)
            return NavigationResult(success=True, url=url, message="ok")
        except Exception as e:
            return NavigationResult(success=False, url=url, message=str(e))
