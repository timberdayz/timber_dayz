from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


class MiaoshouNavigation(NavigationComponent):
    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: OrdersSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or OrdersSelectors()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        if target is not TargetPage.ORDERS:
            return NavigationResult(success=False, message=f"unsupported target: {target}", url=str(getattr(page, 'url', '') or ''))

        cfg = self.ctx.config or {}
        subtype = str(cfg.get("orders_subtype") or "shopee").strip().lower()
        await page.goto(
            self._orders_detail_url(subtype),
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.get_by_text("利润明细", exact=False).first.wait_for(state="visible", timeout=15000)
        return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))
