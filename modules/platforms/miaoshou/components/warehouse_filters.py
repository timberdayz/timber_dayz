from __future__ import annotations

import re
from typing import Any

from modules.components.base import ComponentBase, ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors


class MiaoshouWarehouseFilters(ComponentBase):
    """仓库清单页面的仓库范围筛选器（全选仓库）。"""

    platform = "miaoshou"
    component_type = "filters"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: InventorySelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()

    async def _warehouse_scope_trigger(self, page: Any) -> Any:
        candidates = [
            page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first,
            page.get_by_text(re.compile(r"^仓库\s*:?$", re.IGNORECASE)).first.locator(
                "xpath=following::*[@role='combobox' or self::input][1]"
            ),
            page.get_by_role("combobox").first,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=1500)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库范围筛选器不可见")

    async def _wait_overlay_ready(self, page: Any) -> Any:
        candidates = [
            page.get_by_role("tooltip").last,
            page.locator(".el-select-dropdown:visible").last,
            page.locator(".ant-select-dropdown:visible").last,
            page.locator(".jx-select-dropdown:visible").last,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=2000)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库筛选下拉未出现")

    async def _is_checkbox_selected(self, locator: Any) -> bool:
        try:
            if await locator.is_checked():
                return True
        except Exception:
            pass

        try:
            checked = await locator.evaluate(
                """el => {
                    const root = el.closest(
                        '[role="checkbox"], label, .ant-checkbox-wrapper, .arco-checkbox, .jx-checkbox, .el-checkbox'
                    ) || el;
                    return root.getAttribute('aria-checked') === 'true'
                        || root.className.includes('checked')
                        || !!root.querySelector('input[type="checkbox"]:checked');
                }"""
            )
            return bool(checked)
        except Exception:
            return False

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            try:
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        try:
            trigger = await self._warehouse_scope_trigger(page)
            await trigger.click(timeout=1500)
            overlay = await self._wait_overlay_ready(page)

            full_select = overlay.get_by_role("checkbox", name="全选").first
            try:
                await full_select.wait_for(state="visible", timeout=2000)
            except Exception:
                full_select = overlay.locator("label:has-text('全选') input[type='checkbox']").first
                await full_select.wait_for(state="attached", timeout=2000)

            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                try:
                    await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
                except Exception:
                    await full_select.click(timeout=1000)

            await self._ensure_popup_closed(page)
            return ResultBase(success=True, message="ok", details={"select_all": True})
        except Exception as e:
            return ResultBase(success=False, message=str(e))