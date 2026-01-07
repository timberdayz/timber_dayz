from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult
from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors


class ShopeeNavigation(NavigationComponent):
    """Shopee navigation component for data center pages."""

    # Component metadata
    platform = "shopee"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: AnalyticsSelectors | Any | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or AnalyticsSelectors()

    async def run(self, page: Any, target: Any) -> NavigationResult:  # type: ignore[override]
        if not page:
            return NavigationResult(success=False, url="", message="page is None")

        # 兼容不同模块的 TargetPage（products_config / analytics_config 等）
        def _key(t: Any) -> str:
            try:
                v = getattr(t, "value", None) or getattr(t, "name", None) or str(t)
                return str(v).lower()
            except Exception:
                return str(t).lower()

        key = _key(target)

        account = self.ctx.account
        shop_id = account.get("shop_id") or account.get("cnsc_shop_id")
        base = getattr(self.sel, "base_url", "https://seller.shopee.cn")

        # 目标路径解析：支持四个主要子类型
        path = ""
        if "products_performance" in key or "product" in key:
            path = getattr(self.sel, "performance_path", "/datacenter/product/performance")
        elif "traffic_overview" in key or "traffic" in key:
            path = getattr(self.sel, "overview_path", "/datacenter/traffic/overview")
        elif "order" in key or "orders" in key:
            path = getattr(self.sel, "performance_path", "/datacenter/order/performance")
        elif "finance" in key or "financial" in key:
            path = getattr(self.sel, "overview_path", "/datacenter/finance/overview")
        else:
            return NavigationResult(success=False, url="", message=f"unsupported target: {target}")

        url = f"{base}{path}" + (f"?cnsc_shop_id={shop_id}" if shop_id else "")

        try:
            if self.logger:
                self.logger.info(f"[ShopeeNavigation] goto: {url}")
            # 先尝试快速加载，失败则降级到更宽松的条件
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                if self.logger:
                    self.logger.warning("[ShopeeNavigation] domcontentloaded timeout, trying load")
                await page.goto(url, wait_until="load", timeout=45000)

            await page.wait_for_timeout(1000)
            return NavigationResult(success=True, url=url, message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeNavigation] failed: {e}")
            return NavigationResult(success=False, url=url, message=str(e))

