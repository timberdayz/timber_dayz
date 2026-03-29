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

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        filters = filters or {}
        statuses = list(filters.get("order_statuses") or [])
        select_all = filters.get("select_all", True)

        trigger = page.get_by_role("combobox", name=re.compile(r"订单状态", re.IGNORECASE)).first
        await trigger.click(timeout=1500)
        await self._wait_ready(page)

        if select_all:
            full_select = page.get_by_role("checkbox", name="全选").first
            checked = await full_select.is_checked()
            if not checked:
                await full_select.click(timeout=1000)
        else:
            for status in statuses:
                box = page.get_by_role("checkbox", name=status).first
                if not await box.is_checked():
                    await box.click(timeout=1000)

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        return ResultBase(success=True, message="ok", details={"select_all": select_all, "statuses": statuses})
