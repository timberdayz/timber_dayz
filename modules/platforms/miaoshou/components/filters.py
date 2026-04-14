from __future__ import annotations

import re
from typing import Any

from modules.components.base import ComponentBase, ExecutionContext, ResultBase


class MiaoshouFilters(ComponentBase):
    platform = "miaoshou"
    component_type = "filters"
    data_domain = None
    _ALL_STATUS_SUMMARY_TOKEN = "+ 4"
    _KNOWN_ORDER_STATUS_LABELS = ("待发货", "已发货", "已完成", "售后中", "已关闭")

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _status_overlay(self, page: Any) -> Any | None:
        candidates = [
            lambda: page.get_by_role("tooltip", name=re.compile(r"全选", re.IGNORECASE)).first,
            lambda: page.get_by_role("tooltip").first,
        ]
        for build in candidates:
            try:
                overlay = build()
                await overlay.wait_for(state="visible", timeout=1500)
                return overlay
            except Exception:
                continue
        return None

    async def _wait_ready(self, page: Any) -> Any:
        overlay = await self._status_overlay(page)
        if overlay is not None:
            try:
                await overlay.get_by_role("option").first.wait_for(state="visible", timeout=5000)
            except Exception:
                await overlay.get_by_text("全选", exact=True).first.wait_for(state="visible", timeout=5000)
            return overlay

        full_select = page.get_by_role("checkbox", name="全选").first
        await full_select.wait_for(state="attached", timeout=5000)
        return page

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

    async def _collapsed_summary_already_shows_all_selected(self, page: Any) -> bool:
        try:
            summary = page.get_by_text("订单状态", exact=True).first.locator("xpath=ancestor::*[1]").first
            summary_text = " ".join(((await summary.text_content()) or "").split())
        except Exception:
            return False

        if self._ALL_STATUS_SUMMARY_TOKEN not in summary_text:
            return False
        return any(label in summary_text for label in self._KNOWN_ORDER_STATUS_LABELS)

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        filters = filters or {}
        statuses = list(filters.get("order_statuses") or [])
        select_all = filters.get("select_all", True)

        if select_all and await self._collapsed_summary_already_shows_all_selected(page):
            return ResultBase(success=True, message="ok", details={"select_all": select_all, "statuses": statuses, "skipped": True})

        trigger = page.get_by_role("combobox", name=re.compile(r"^订单状态\s*[:：]?$", re.IGNORECASE)).first
        await trigger.click(timeout=1500)
        overlay = await self._wait_ready(page)

        if select_all:
            full_select = overlay.get_by_role("checkbox", name="全选").first
            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                try:
                    await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
                except Exception:
                    await full_select.click(timeout=1000)
        else:
            for status in statuses:
                box = overlay.get_by_role("checkbox", name=status).first
                if not await self._is_checkbox_selected(box):
                    try:
                        await overlay.get_by_role("option", name=status).first.click(timeout=1000)
                    except Exception:
                        await box.click(timeout=1000)

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        return ResultBase(success=True, message="ok", details={"select_all": select_all, "statuses": statuses})
