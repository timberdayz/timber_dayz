from __future__ import annotations

import re
from typing import Any

from modules.components.base import ComponentBase, ExecutionContext, ResultBase


class MiaoshouFilters(ComponentBase):
    platform = "miaoshou"
    component_type = "filters"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _wait_ready(self, page: Any) -> None:
        full_select = page.get_by_role("checkbox", name="全选").first
        await full_select.wait_for(state="visible", timeout=5000)

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

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        filters = filters or {}
        statuses = list(filters.get("order_statuses") or [])
        select_all = filters.get("select_all", True)

        trigger = page.get_by_role("combobox", name=re.compile(r"^订单状态\s*[:：]?$", re.IGNORECASE)).first
        await trigger.click(timeout=1500)
        await self._wait_ready(page)

        if select_all:
            full_select = page.get_by_role("checkbox", name="全选").first
            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                await full_select.click(timeout=1000)
        else:
            for status in statuses:
                box = page.get_by_role("checkbox", name=status).first
                if not await self._is_checkbox_selected(box):
                    await box.click(timeout=1000)

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        return ResultBase(success=True, message="ok", details={"select_all": select_all, "statuses": statuses})
