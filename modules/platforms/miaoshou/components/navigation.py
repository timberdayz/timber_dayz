from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors

DEFAULT_BASE_URL: str = "https://erp.91miaoshou.com"
DEFAULT_DEEP_LINK_TEMPLATE: str = "/stat/profit_statistics/detail?platform={platform}"
DEFAULT_WAREHOUSE_CHECKLIST_PATH: str = "/warehouse/checklist"


@dataclass(frozen=True)
class _DefaultNavSelectors:
    """Lightweight selectors used as the default for ``MiaoshouNavigation``.

    This avoids a hard import on the legacy ``warehouse_config`` module while
    preserving the navigation URL helpers needed by ``TargetPage.ORDERS`` and
    ``TargetPage.WAREHOUSE_CHECKLIST``.
    """

    base_url: str = DEFAULT_BASE_URL
    deep_link_template: str = DEFAULT_DEEP_LINK_TEMPLATE
    checklist_path: str = DEFAULT_WAREHOUSE_CHECKLIST_PATH


class MiaoshouNavigation(NavigationComponent):
    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: OrdersSelectors | _DefaultNavSelectors | None = None,
    ) -> None:
        super().__init__(ctx)
        self.sel: Any = selectors or _DefaultNavSelectors()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    def _warehouse_checklist_url(self) -> str:
        return f"{self.sel.base_url}{self.sel.checklist_path}"

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        if target is TargetPage.ORDERS:
            cfg = self.ctx.config or {}
            subtype = str(cfg.get("orders_subtype") or "shopee").strip().lower()
            await page.goto(
                self._orders_detail_url(subtype),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("利润明细", exact=False).first.wait_for(state="visible", timeout=15000)
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))

        if target is TargetPage.WAREHOUSE_CHECKLIST:
            await page.goto(
                self._warehouse_checklist_url(),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("仓库清单", exact=False).first.wait_for(state="visible", timeout=15000)
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))

        return NavigationResult(success=False, message=f"unsupported target: {target}", url=str(getattr(page, "url", "") or ""))
