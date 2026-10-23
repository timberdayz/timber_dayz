from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import (
    NavigationComponent,
    NavigationResult,
    TargetPage,
)
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors

DEFAULT_BASE_URL: str = "https://erp.91miaoshou.com"
DEFAULT_DEEP_LINK_TEMPLATE: str = "/stat/profit_statistics/detail?platform={platform}"
DEFAULT_WAREHOUSE_CHECKLIST_PATH: str = "/warehouse/checklist"
DEFAULT_PURCHASE_PATH: str = "/purchase/goods"


@dataclass(frozen=True)
class _DefaultNavSelectors:
    """Lightweight selectors used as the default for ``MiaoshouNavigation``.

    This avoids a hard import on the legacy ``warehouse_config`` module while
    preserving the navigation URL helpers needed by ``TargetPage.ORDERS``,
    ``TargetPage.WAREHOUSE_CHECKLIST`` and ``TargetPage.PURCHASE``.
    """

    base_url: str = DEFAULT_BASE_URL
    deep_link_template: str = DEFAULT_DEEP_LINK_TEMPLATE
    checklist_path: str = DEFAULT_WAREHOUSE_CHECKLIST_PATH
    purchase_path: str = DEFAULT_PURCHASE_PATH


class MiaoshouNavigation(NavigationComponent):
    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: (
            OrdersSelectors
            | _DefaultNavSelectors
            | InventorySelectors
            | PurchaseSelectors
            | None
        ) = None,
    ) -> None:
        super().__init__(ctx)
        self.sel: Any = selectors or _DefaultNavSelectors()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    def _warehouse_checklist_url(self) -> str:
        return f"{self.sel.base_url}{self.sel.checklist_path}"

    def _purchase_goods_url(self) -> str:
        purchase_path = getattr(self.sel, "purchase_path", DEFAULT_PURCHASE_PATH)
        base_url = getattr(self.sel, "base_url", DEFAULT_BASE_URL)
        # 默认用 URL 参数显式表达 "全部" tab，避免依赖 UI click。
        # 对应 orders 用 ?platform=shopee 表达 subtype 的设计哲学。
        tab_param = getattr(self.sel, "purchase_tab_param", "all")
        return f"{base_url}{purchase_path}?tab={tab_param}"

    def _detect_checklist_route_signal(self, page: Any, previous_url: str) -> bool:
        """路由特征信号：URL 命中仓库清单路径，或相对导航前路由已切换。

        - 强信号：URL 含 `checklist_path`（如 ``/warehouse/checklist``）
        - 弱信号：URL 相对导航前**已切换**（SPA 路由切换不带路径时的兜底）
        """
        current_url = str(getattr(page, "url", "") or "")
        checklist_path = str(getattr(self.sel, "checklist_path", "") or "")
        if checklist_path and checklist_path in current_url:
            return True
        if not current_url:
            return False
        # current_url 非空即说明 page.url 存在，直接比较属性即可
        return page.url != previous_url

    async def _detect_checklist_element_signal(self, page: Any) -> bool:
        """关键元素信号：「仓库清单」标题可见。"""
        element_ok = True
        try:
            await page.get_by_text("仓库清单", exact=False).first.wait_for(
                state="visible", timeout=15000
            )
        except Exception as exc:
            # 元素信号缺失不直接抛错：交给双信号判定统一产出可诊断信息
            element_ok = False
            logger = self.logger
            if logger:
                logger.info(f"仓库清单元素信号缺失: {exc}")
        return element_ok

    async def _wait_warehouse_checklist_ready(
        self, page: Any, previous_url: str
    ) -> str:
        """仓库清单页就绪判定：**双信号**（《规范》§13.2）。

        路由特征信号与关键元素信号**都满足**才算就绪；缺任一信号都返回
        可诊断的失败说明（明确指出缺哪个信号 + 当前 URL）。
        返回空字符串表示就绪。
        """
        element_ok = await self._detect_checklist_element_signal(page)
        route_ok = self._detect_checklist_route_signal(page, previous_url)
        if route_ok and element_ok:
            return ""

        current_url = str(getattr(page, "url", "") or "")
        checklist_path = str(getattr(self.sel, "checklist_path", "") or "")
        missing: list[str] = []
        if not route_ok:
            missing.append(f"route_signal(checklist_path={checklist_path})")
        if not element_ok:
            missing.append("element_signal(text=仓库清单)")
        return (
            "warehouse_checklist_ready_failed: 缺少就绪信号 "
            + ", ".join(missing)
            + f" current_url={current_url}"
        )

    async def _navigate_warehouse_checklist(self, page: Any) -> NavigationResult:
        """导航到仓库清单：URL/路由特征 + 关键元素可见（双信号）。"""
        previous_url = str(getattr(page, "url", "") or "")
        await page.goto(
            self._warehouse_checklist_url(),
            wait_until="domcontentloaded",
            timeout=60000,
        )
        failure = await self._wait_warehouse_checklist_ready(page, previous_url)
        if failure:
            return NavigationResult(
                success=False,
                message=failure,
                url=str(getattr(page, "url", "") or ""),
            )
        await self.stabilize_safe_notices(page, label="post-navigation cleanup")
        return NavigationResult(
            success=True, message="ok", url=str(getattr(page, "url", "") or "")
        )

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        if target is TargetPage.ORDERS:
            cfg = self.ctx.config or {}
            subtype = str(cfg.get("orders_subtype") or "shopee").strip().lower()
            await page.goto(
                self._orders_detail_url(subtype),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("利润明细", exact=False).first.wait_for(
                state="visible", timeout=15000
            )
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(
                success=True, message="ok", url=str(getattr(page, "url", "") or "")
            )

        if target is TargetPage.WAREHOUSE_CHECKLIST:
            return await self._navigate_warehouse_checklist(page)

        if target is TargetPage.PURCHASE:
            await page.goto(
                self._purchase_goods_url(),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("采购单", exact=False).first.wait_for(
                state="visible", timeout=15000
            )
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(
                success=True, message="ok", url=str(getattr(page, "url", "") or "")
            )

        return NavigationResult(
            success=False,
            message=f"unsupported target: {target}",
            url=str(getattr(page, "url", "") or ""),
        )
