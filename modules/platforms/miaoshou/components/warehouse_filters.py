from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.apps.collection_center.retry_strategy import RetryStrategy
from modules.components.base import ComponentBase, ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors


async def _is_visible(locator: Any) -> bool:
    """locator 当前是否可见（检测失败按「不可见」处理，不抛）。"""
    visible = True
    try:
        visible = await locator.is_visible()
    except Exception:
        # 可见性检测失败按「不可见」处理，交由调用方继续走等待路径
        visible = False
    return visible


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

        候选按证据强度排序（依据见 `inventory_config.py` 顶部取证说明）：
        1. `.jx-select__wrapper` —— 归档 `export.py:368` 实战验证过能点开下拉
        2. `.jx-select`（精确 class token）—— 最外层外壳
        3. 宽松 `contains(@class,'jx-select')` —— 防改版兜底
        """
        try:
            label_input = page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first
            await label_input.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
        except Exception as e:
            self._log(f"[warehouse_filters] 层A 触发器定位不可用: {e}")
            return None

        xpaths = (
            self.sel.warehouse_scope_wrapper_xpath,
            self.sel.warehouse_scope_container_xpath,
            self.sel.warehouse_scope_container_xpath_loose,
        )
        for xpath in xpaths:
            try:
                container = label_input.locator(xpath)
                await container.wait_for(
                    state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return container
            except Exception as e:
                self._log(f"[warehouse_filters] 层A 容器候选不可用 ({xpath}): {e}")
        return None

    async def _scope_all_selected_root(self, page: Any) -> Any | None:
        """层 C 专用的容器解析：优先取**最外层** `.jx-select`。

        与层 A 分开的原因：层 A 点的是 `.jx-select__wrapper`（内层外壳），
        而 `.jx-select__selected-item` 是 **`.jx-select`（最外层）的后代**
        （证据：订单域 `filters.py:78-83` 用 `page.locator(".jx-select")`
        再 `.locator(".jx-select__selected-item")` 命中）。
        用层 A 的 wrapper 去查，可能查不到选中区 → 层 C 恒不命中。
        """
        try:
            label_input = page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first
            await label_input.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
        except Exception as e:
            self._log(f"[warehouse_filters] 层C 触发器定位不可用: {e}")
            return None

        for xpath in (
            self.sel.warehouse_scope_container_xpath,
            self.sel.warehouse_scope_container_xpath_loose,
            self.sel.warehouse_scope_wrapper_xpath,
        ):
            try:
                container = label_input.locator(xpath)
                await container.wait_for(
                    state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return container
            except Exception as e:
                self._log(f"[warehouse_filters] 层C 容器候选不可用 ({xpath}): {e}")
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
        container = await self._scope_all_selected_root(page)
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

    async def _pre_check_scope_already_all_selected(self, page: Any) -> bool:
        """pre-check：层 C「已全选」检测（命中即说明不需要再开下拉勾选）。

        层 C 判定本身是**尽力而为**，只有命中才跳过；未命中一律继续走
        A → B → D 四层防护（《规范》§3.5「前置检测」）。
        """
        if await self._scope_already_all_selected(page):
            self._log("[warehouse_filters] 层C 命中已全选，跳过开下拉")
            return True
        return False

    async def _open_scope_dropdown(self, page: Any) -> None:
        """action：按 A → B → D 打开仓库范围下拉框。

        - A 点 .jx-select 容器外壳（治本）
        - B force=True 穿透 + 有界重试
        - D 键盘兜底（仅 A / B 均失败后触发）

        全部失败时抛 RuntimeError，消息带阶段名 warehouse_scope_open_failed。
        """
        trigger = await self._warehouse_scope_trigger(page)

        container = await self._warehouse_scope_container(page)
        if container is not None:
            try:
                await container.click(
                    timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                await self._wait_overlay_ready(page)
                return
            except Exception as e:
                self._log(f"[warehouse_filters] 层A 打开下拉失败: {e}")

        try:
            await self._click_trigger_with_retry(trigger)
            await self._wait_overlay_ready(page)
            return
        except Exception as e:
            self._log(f"[warehouse_filters] 层B 打开下拉失败: {e}")
            layer_b_error = e

        try:
            await self._keyboard_open(page, trigger)
            await self._wait_overlay_ready(page)
            return
        except Exception as e:
            raise RuntimeError(
                "warehouse_scope_open_failed: 层A/层B/层D 均无法打开仓库范围下拉框"
                f"（层B: {layer_b_error}; 层D: {e}）"
            ) from layer_b_error

    def _scope_overlay_candidates(self, page: Any) -> list[Any]:
        """仓库范围下拉浮层的定位候选（按证据强度排序）。

        候选来源（依据见 `inventory_config.py` 顶部取证说明）：
        - `role="listbox"`：真实 call log 里 input 声明了 `aria-haspopup="listbox"`
          与 `aria-controls="jx-id-..."`，说明浮层是 listbox 角色
        - `.jx-select-dropdown` / `.jx-select__dropdown` / `.jx-popper`：
          归档 `export.py:386-390` 实战验证过的浮层 class
        - `tooltip` / `el-select-dropdown` / `ant-select-dropdown`：历史兼容候选
        """
        return [
            page.get_by_role("listbox").last,
            *[
                page.locator(selector).last
                for selector in self.sel.warehouse_scope_overlay_selectors
            ],
            page.get_by_role("tooltip").last,
            page.locator(".el-select-dropdown:visible").last,
            page.locator(".ant-select-dropdown:visible").last,
        ]

    async def _wait_overlay_ready(self, page: Any) -> Any:
        """定位已打开的仓库范围下拉浮层（带可见性等待）。"""
        for locator in self._scope_overlay_candidates(page):
            try:
                await locator.wait_for(state="visible", timeout=2000)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库筛选下拉未出现")

    async def _locate_scope_overlay(self, page: Any) -> Any:
        """关键交互前**重新定位**仓库范围下拉浮层（《规范》§13.3）。

        优先用「当前已可见」的候选（不等待、不改变时序）；都不可见时退回
        带等待的 `_wait_overlay_ready`（与既有行为一致）。
        """
        for locator in self._scope_overlay_candidates(page):
            if await _is_visible(locator):
                return locator
        return await self._wait_overlay_ready(page)

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

    async def _find_full_select_checkbox(self, overlay: Any) -> Any:
        """在浮层里找「全选」复选框。

        候选顺序（依据见 `inventory_config.py` 顶部取证说明）：
        1. `role="checkbox"` + 名称「全选」—— 语义定位
        2. `label:has-text('全选') input[type='checkbox']` —— 历史兼容
        3. `.jx-select-dropdown__header .jx-checkbox` → `.jx-checkbox__input`
           —— 归档 `export.py:396-399` 实战写法（浮层头部就是「全选」行）
        """
        candidates = [
            overlay.get_by_role("checkbox", name="全选").first,
            overlay.locator("label:has-text('全选') input[type='checkbox']").first,
            overlay.locator(self.sel.warehouse_scope_full_select_header_selector).first,
        ]
        for candidate in candidates:
            try:
                await candidate.wait_for(state="visible", timeout=2000)
                return candidate
            except Exception:
                continue
        # 最后的兜底：让调用方拿到一个能 raise 的 locator，错误信息更明确
        return candidates[0]

    async def _ensure_scope_all_selected(self, page: Any) -> None:
        """action 的一部分：在下拉浮层里把「全选」勾上。

        浮层在关键交互前**重新定位**，不跨阶段持有 locator（《规范》§13.3）。
        """
        overlay = await self._locate_scope_overlay(page)
        full_select = await self._find_full_select_checkbox(overlay)

        checked = await self._is_checkbox_selected(full_select)
        if not checked:
            try:
                await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
            except Exception:
                await full_select.click(timeout=1000)

    async def _post_check_scope_all_selected(self, page: Any) -> None:
        """post-check：动作后**回读**「全选」复选框的勾选状态。

        动作成功 ≠ 业务成功（《规范》§3.5.1）：没勾上就是失败，抛带阶段前缀的
        错误 warehouse_scope_verify_failed。
        """
        selected = False
        try:
            overlay = await self._locate_scope_overlay(page)
            full_select = await self._find_full_select_checkbox(overlay)
            selected = await self._is_checkbox_selected(full_select)
        except Exception as e:
            # 回读通道本身失败（如浮层已关闭）同样按「未确认生效」处理
            raise RuntimeError(
                f"warehouse_scope_verify_failed: 回读「全选」勾选状态失败（{e}）"
            ) from e
        if not selected:
            raise RuntimeError(
                "warehouse_scope_verify_failed: 「全选」复选框回读仍未选中"
            )

    async def _action_select_scope_all(self, page: Any) -> None:
        """action：打开仓库范围下拉框并勾上「全选」（A/B/C/D 四层防护保持不变）。"""
        await self._open_scope_dropdown(page)
        await self._ensure_scope_all_selected(page)

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        try:
            await self.report_step(
                "step_start", step_id="warehouse_scope_ready", action="打开仓库范围筛选"
            )
            # ── pre-check：已全选则不需要再开下拉勾选 ──
            if await self._pre_check_scope_already_all_selected(page):
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

            # ── action：开下拉 + 勾「全选」 ──
            await self._action_select_scope_all(page)

            # ── post-check：回读勾选状态，确认真的生效 ──
            await self._post_check_scope_all_selected(page)

            await self._ensure_popup_closed(page)
            await self.report_step(
                "step_success", step_id="warehouse_scope_ready", action="仓库范围已全选"
            )
            return ResultBase(success=True, message="ok", details={"select_all": True})
        except Exception as e:
            screenshot_path = await self._capture_failure_screenshot(
                page, "warehouse_scope"
            )
            message = str(e)
            if screenshot_path:
                message = f"{message} (screenshot: {screenshot_path})"
            await self.report_step(
                "step_failed",
                step_id="warehouse_scope_ready",
                action="仓库范围筛选失败",
                error=message,
                screenshot_path=screenshot_path or "",
            )
            return ResultBase(success=False, message=message)

    async def _capture_failure_screenshot(self, page: Any, stage: str) -> str | None:
        """失败时截图落盘到 ctx.config['task']['screenshot_dir']。

        截图失败不得影响主流程。
        """
        screenshot_dir = ""
        config = self.ctx.config or {}
        task_cfg = config.get("task") if isinstance(config, dict) else None
        if isinstance(task_cfg, dict):
            screenshot_dir = str(task_cfg.get("screenshot_dir") or "")
        if not screenshot_dir:
            return None

        try:
            target_dir = Path(screenshot_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = target_dir / f"miaoshou_{stage}_{stamp}.png"
            await page.screenshot(path=str(path))
            return str(path)
        except Exception as e:
            logger = self.logger
            if logger:
                logger.warning(f"warehouse filters 截图失败（已忽略）: {e}")
            return None
