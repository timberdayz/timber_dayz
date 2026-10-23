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
        """判断"订单状态"是否已选了多个状态（大概率已全选）。

        妙手 jx-select 多选模式下，选中 ≥ 2 个状态时 selected-item 区域会
        渲染：第 1 个状态标签（完整文本，如"待发货"）+ 1 个"+ N"折叠提示
        标签（也是 jx-tag）。这里只看 DOM 结构，不依赖任何文本内容，
        不会被 label 文本渲染方式、`+ 4` token 是否出现、状态标签是否
        被截断等因素影响。
        """
        try:
            containers = page.locator(".jx-select")
            count = await containers.count()
            for i in range(count):
                try:
                    container = containers.nth(i)
                    selected = container.locator(".jx-select__selected-item").first
                    if await selected.count() == 0:
                        continue
                    tags = selected.locator(".jx-tag")
                    tag_count = await tags.count()
                    if tag_count < 2:
                        continue
                    # 检查是否存在以"+ "开头的折叠提示标签（妙手 jx-select
                    # 选中 ≥ 2 个时会折叠成"+ N"标签）
                    for j in range(tag_count):
                        tag_text = (await tags.nth(j).text_content() or "").strip()
                        if tag_text.startswith("+ "):
                            return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        filters = filters or {}
        statuses = list(filters.get("order_statuses") or [])
        select_all = filters.get("select_all", True)

        if select_all and await self._collapsed_summary_already_shows_all_selected(page):
            return ResultBase(success=True, message="ok", details={"select_all": select_all, "statuses": statuses, "skipped": True})

        trigger = page.get_by_role("combobox", name=re.compile(r"^订单状态\s*[:：]?$", re.IGNORECASE)).first
        # 全选状态下 selected-item 区域堆着 jx-tag,盖住 trigger(input)
        # 的可点击区。force=True 穿透遮挡点击；万一还失败,重试 1 次。
        clicked = False
        for _ in range(2):
            try:
                await trigger.click(timeout=1500, force=True)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("无法点开订单状态下拉框")
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
