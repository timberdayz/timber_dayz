from __future__ import annotations

import re
from typing import Any

from modules.apps.collection_center.retry_strategy import RetryStrategy
from modules.components.base import ComponentBase, ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors


class MiaoshouWarehouseFilters(ComponentBase):
    """仓库清单页面的仓库范围筛选器（全选仓库）。"""

    platform = "miaoshou"
    component_type = "filters"
    data_domain = None

    def __init__(
        self, ctx: ExecutionContext, selectors: InventorySelectors | None = None
    ) -> None:
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
                await locator.wait_for(
                    state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库范围筛选器不可见")

    def _log(self, message: str) -> None:
        logger = self.logger
        if logger:
            logger.info(message)

    async def _warehouse_scope_container(self, page: Any) -> Any | None:
        """层 A：由「仓库」标签语义锚点收敛到所属 .jx-select 容器外壳。

        点容器外壳而不是被 selected-item 覆盖的 .jx-select__input，是形态 A 的治本手段。
        返回 None 表示层 A 不可用（DOM 形态未取证 / 改版），由层 B 兜底。
        """
        try:
            label_input = page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first
            await label_input.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
            container = label_input.locator(self.sel.warehouse_scope_container_xpath)
            await container.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
            return container
        except Exception as e:
            self._log(f"[warehouse_filters] 层A 容器定位不可用: {e}")
            return None

    async def _scope_already_all_selected(self, page: Any) -> bool:
        """层 C：已全选前置检测（尽力而为，**不得作为唯一防线**）。

        ⚠️ **不使用裸 `.jx-select` 全页扫描**：仓库清单页可能有多个
        jx-select（店铺 / 分类等），任一 select 处于 "+ N" 折叠态就会误判
        「仓库已全选」→ 直接跳过开下拉 → **导出数据范围错误**。
        必须复用层 A 的 label→容器收敛路径，**只检查「仓库」这一个 select**。

        仓库筛选是「全选仓库」单复选框；已全选时折叠区会渲染 "+ N" 折叠标签。
        ⚠️ 该 DOM 形态未经真实页面取证，可能恒为 False；因此只有命中才跳过，
        未命中一律继续走 A → B → D。
        """
        container = await self._warehouse_scope_container(page)
        if container is None:
            return False

        try:
            selected = container.locator(".jx-select__selected-item").first
            if await selected.count() == 0:
                return False
            tags = selected.locator(".jx-tag")
            tag_count = await tags.count()
            if tag_count < 2:
                # 只有一个标签 = 只选了一项 ≠ 全选（与订单域 filters.py 的守卫一致）
                return False
            for tag_index in range(tag_count):
                text = (await tags.nth(tag_index).text_content() or "").strip()
                if text.startswith("+ "):
                    return True
        except Exception as e:
            self._log(f"[warehouse_filters] 层C 判定失败: {e}")
        return False

    async def _force_click(self, trigger: Any) -> None:
        """层 B 的单次尝试：force=True 穿透遮挡点击。"""
        await trigger.click(
            timeout=self.sel.warehouse_scope_trigger_timeout_ms, force=True
        )

    async def _click_trigger_with_retry(self, trigger: Any) -> None:
        """层 B：force=True 穿透遮挡 + 有界重试。

        使用既有 RetryStrategy（《规范》§6 要求用既有重试机制，不自造内联循环）。
        """
        retry = RetryStrategy()
        await retry.execute_with_retry(
            self._force_click,
            trigger,
            retry_config={
                "max_attempts": self.sel.warehouse_scope_open_max_attempts,
                "backoff_strategy": "fixed",
                "backoff_base": self.sel.warehouse_scope_retry_backoff_seconds,
            },
            step_id="warehouse_scope_open",
        )

    async def _keyboard_open(self, page: Any, trigger: Any) -> None:
        """层 D：键盘兜底（**仅在层 A / 层 B 均失败后触发**）。

        工程兜底，《规范》未覆盖此场景。jx-select 是否响应 Enter 需批次 2 取证确认。
        """
        try:
            await trigger.focus(timeout=self.sel.warehouse_scope_trigger_timeout_ms)
        except Exception as e:
            self._log(f"[warehouse_filters] 层D focus 失败: {e}")
        await page.keyboard.press("Enter")

    async def _open_scope_dropdown(self, page: Any) -> Any | None:
        """按 C → A → B → D 打开仓库范围下拉框，返回浮层容器。

        - C 已全选前置检测：命中即跳过开下拉（返回 None）
        - A 点 .jx-select 容器外壳（治本）
        - B force=True 穿透 + 有界重试
        - D 键盘兜底（仅 A / B 均失败后触发）

        全部失败时抛 RuntimeError，消息带阶段名 warehouse_scope_open_failed。
        """
        if await self._scope_already_all_selected(page):
            self._log("[warehouse_filters] 层C 命中已全选，跳过开下拉")
            return None

        trigger = await self._warehouse_scope_trigger(page)

        container = await self._warehouse_scope_container(page)
        if container is not None:
            try:
                await container.click(
                    timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return await self._wait_overlay_ready(page)
            except Exception as e:
                self._log(f"[warehouse_filters] 层A 打开下拉失败: {e}")

        try:
            await self._click_trigger_with_retry(trigger)
            return await self._wait_overlay_ready(page)
        except Exception as e:
            self._log(f"[warehouse_filters] 层B 打开下拉失败: {e}")
            layer_b_error = e

        try:
            await self._keyboard_open(page, trigger)
            return await self._wait_overlay_ready(page)
        except Exception as e:
            raise RuntimeError(
                "warehouse_scope_open_failed: 层A/层B/层D 均无法打开仓库范围下拉框"
                f"（层B: {layer_b_error}; 层D: {e}）"
            ) from layer_b_error

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
            await self.report_step(
                "step_start", step_id="warehouse_scope_ready", action="打开仓库范围筛选"
            )
            overlay = await self._open_scope_dropdown(page)
            if overlay is None:
                await self.report_step(
                    "step_success",
                    step_id="warehouse_scope_ready",
                    action="仓库范围已全选，跳过开下拉",
                )
                return ResultBase(
                    success=True,
                    message="ok",
                    details={"select_all": True, "skipped": True},
                )

            full_select = overlay.get_by_role("checkbox", name="全选").first
            try:
                await full_select.wait_for(state="visible", timeout=2000)
            except Exception:
                full_select = overlay.locator(
                    "label:has-text('全选') input[type='checkbox']"
                ).first
                await full_select.wait_for(state="attached", timeout=2000)

            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                try:
                    await overlay.get_by_text("全选", exact=True).first.click(
                        timeout=1000
                    )
                except Exception:
                    await full_select.click(timeout=1000)

            await self._ensure_popup_closed(page)
            await self.report_step(
                "step_success", step_id="warehouse_scope_ready", action="仓库范围已全选"
            )
            return ResultBase(success=True, message="ok", details={"select_all": True})
        except Exception as e:
            await self.report_step(
                "step_failed",
                step_id="warehouse_scope_ready",
                action="仓库范围筛选失败",
                error=str(e),
            )
            return ResultBase(success=False, message=str(e))
