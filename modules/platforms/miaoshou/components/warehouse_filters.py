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


def _warehouse_label_input(page: Any) -> Any:
    """「仓库」文案对应的表单输入（层 B 兜底路径的入口）。

    `get_by_label` 在 Playwright 与测试替身里都是**惰性构造**——只产出
    Locator、不做 DOM 查询，因此不会抛异常，这里不需要 try/except 包裹。
    """
    # 业务语义：按表单标签「仓库」定位输入控件，页面首个匹配即仓库筛选
    return page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first


def _field_scoped_select(page: Any, sel: InventorySelectors) -> Any:
    """仓库 select 根节点：实证锚点 `[data-field='warehouseIds']` 下的 `.jx-select`。

    锚点下**只有这一个** `.jx-select`，所以取第一个是确定的，不存在
    「取到别的 select」的歧义（对比裸 `.jx-select` 全页扫描的风险）。
    """
    # 业务语义：锚点下唯一的 .jx-select
    return page.locator(f"{sel.warehouse_scope_field_selector} .jx-select").first


def _scope_container_candidates(page: Any, sel: InventorySelectors) -> list[Any]:
    """层 A 的容器候选（按证据强度排序）。

    1. `[data-field='warehouseIds'] .jx-select__wrapper` —— 实证锚点 + 归档验证过的点击目标
    2. `[data-field='warehouseIds'] .jx-select` —— 实证锚点 + 最外层外壳
    3~5. 「仓库」文案 → 最近 `.jx-select__wrapper` / `.jx-select` / 宽松兜底
    """
    field = sel.warehouse_scope_field_selector
    label_input = _warehouse_label_input(page)
    return [
        # 业务语义：锚点下的 .jx-select__wrapper 唯一
        page.locator(f"{field} .jx-select__wrapper").first,
        _field_scoped_select(page, sel),
        label_input.locator(sel.warehouse_scope_wrapper_xpath),
        label_input.locator(sel.warehouse_scope_container_xpath),
        label_input.locator(sel.warehouse_scope_container_xpath_loose),
    ]


def _scope_root_candidates(page: Any, sel: InventorySelectors) -> list[Any]:
    """层 C 的根节点候选（实证锚点优先，文案兜底）。"""
    label_input = _warehouse_label_input(page)
    return [
        _field_scoped_select(page, sel),
        label_input.locator(sel.warehouse_scope_container_xpath),
        label_input.locator(sel.warehouse_scope_container_xpath_loose),
        label_input.locator(sel.warehouse_scope_wrapper_xpath),
    ]


def _scope_overlay_candidates(page: Any, sel: InventorySelectors) -> list[Any]:
    """仓库范围下拉浮层的定位候选（按证据强度排序）。

    2026-10-23 真实页面取证，浮层真实结构::

        div.jx-select-dropdown.is-multiple.pro-select-popper
          ├── div.jx-select-dropdown__header      ← 「全选」复选框在这里
          └── div.jx-scrollbar
                └── ul.jx-select-dropdown__list[role=listbox]   ← 5 个仓库行

    ⚠️ `role="listbox"` 指的是**内层 ul**，它**不含** header 的复选框；
    所以 `.jx-select-dropdown`（外层 div）必须排在 listbox **之前**，
    否则「全选」复选框永远找不到（这正是历史实现失效的根因）。
    """
    return [
        *[
            page.locator(selector).last
            for selector in sel.warehouse_scope_overlay_selectors
        ],
        page.get_by_role("listbox").last,
        page.get_by_role("tooltip").last,
        page.locator(".el-select-dropdown:visible").last,
        page.locator(".ant-select-dropdown:visible").last,
    ]


def _full_select_checkbox_candidates(
    overlay: Any, sel: InventorySelectors
) -> list[Any]:
    """「全选」复选框的候选定位。

    2026-10-23 真实页面取证（浮层头部结构）::

        div.jx-select-dropdown__header
          └── label.jx-checkbox.jx-checkbox--small.is-checked.pro-checkbox
                ├── input.jx-checkbox__original[type=checkbox]
                └── span.jx-checkbox__label「全选」

    ⚠️ 三个实测结论决定了候选顺序：

    1. ``get_by_role("checkbox", name="全选")`` **命中 0 个**——复选框不是
       ``role="checkbox"``，名字也不是「全选」（只有表格选择列的复选框叫
       「选择所有行」/「选择当前行」）。
    2. 必须传入**外层** ``.jx-select-dropdown`` 作为浮层根——取内层 listbox
       会因为拿不到 header 而永远找不到「全选」。
    3. **``input.jx-checkbox__original`` 能定位（count=1）但点不到**——它是
       视觉隐藏的真实 input，Playwright 的 actionability 检查会超时。
       实测**可点击目标是 ``label.jx-checkbox``**（点击后
       ``modelvaluegroup`` 真的由 5 个仓库 ID 变空串，再点又恢复），
       所以 label 排第一；input 只保留作兜底。
    """
    header = sel.warehouse_scope_full_select_header_selector
    checkbox_input = sel.warehouse_scope_checkbox_input_selector
    return [
        # 业务语义：浮层头部只有一个「全选」复选框
        overlay.locator(header).first,
        # 业务语义：同一个复选框里的真实 input（隐藏，仅兜底）
        overlay.locator(f"{header} {checkbox_input}").first,
        # 业务语义：按无障碍角色兜底查找同名复选框
        overlay.get_by_role("checkbox", name="全选").first,
    ]


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
            _warehouse_label_input(page),
            # 业务语义：文案锚点之后的第一个 combobox/input
            page.get_by_text(re.compile(r"^仓库\s*:?$", re.IGNORECASE)).first.locator(
                "xpath=following::*[@role='combobox' or self::input][1]"
            ),
            # 业务语义：仓库筛选是页面上第一个 combobox（按 DOM 顺序）
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
        """层 A：收敛到仓库筛选的 .jx-select 容器外壳。

        点容器外壳而不是被 selected-item 覆盖的 .jx-select__input，是形态 A 的治本手段。

        优先用**实证的稳定锚点** `[data-field='warehouseIds']`
        （2026-10-23 真实页面取证），不再靠「仓库」文案猜最近祖先；
        文案路径保留为妙手改版后的兜底。
        返回 None 表示层 A 不可用，由层 B 兜底。
        """
        for locator in _scope_container_candidates(page, self.sel):
            try:
                await locator.wait_for(
                    state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return locator
            except Exception as e:
                self._log(f"[warehouse_filters] 层A 容器候选不可用: {e}")
        return None

    async def _scope_all_selected_root(self, page: Any) -> Any | None:
        """层 C 专用的容器解析：仓库 select 根节点。

        与层 A 分开的原因：层 A 点的是 `.jx-select__wrapper`（内层外壳），
        而选中区 / `modelvaluegroup` 在 **`.jx-select`（最外层）** 上
        （2026-10-23 实测：`div.jx-select.jx-select--small.pro-select` 带
        `modelvaluegroup="684506,563787,563786,381635,299699"`）。
        """
        for locator in _scope_root_candidates(page, self.sel):
            try:
                await locator.wait_for(
                    state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
                )
                return locator
            except Exception as e:
                self._log(f"[warehouse_filters] 层C 容器候选不可用: {e}")
        return None

    async def _scope_already_all_selected(self, page: Any) -> bool:
        """层 C：已全选前置检测（尽力而为，**不得作为唯一防线**）。

        2026-10-23 真实页面取证（仓库清单页）：

        - 仓库 select 根节点 `div.jx-select` 带 `modelvaluegroup` 属性，
          全选态 = ``"684506,563787,563786,381635,299699"``，空态 = 空串；
        - 全选态渲染 **2 个** `.jx-tag`（首个仓库名 + 「+ N」折叠标签），空态 0 个。

        ⚠️ **不使用裸 `.jx-select` 全页扫描**：仓库清单页有多个 jx-select
        （商品SKU / 模糊匹配 / 中文名称…），任一 select 处于 "+ N" 折叠态就会误判
        「仓库已全选」→ 直接跳过开下拉 → **导出数据范围错误**。
        必须只检查「仓库」这一个 select。
        """
        container = await self._scope_all_selected_root(page)
        if container is None:
            return False

        try:
            selected_values = await container.get_attribute(
                self.sel.warehouse_scope_selected_value_attr
            )
            if selected_values and selected_values.strip():
                return True
        except Exception as e:
            self._log(f"[warehouse_filters] 层C 选中值属性读取失败: {e}")

        try:
            tags = container.locator(".jx-tag")
            tag_count = await tags.count()
            if tag_count < 2:
                # 只有一个标签 = 只选了一项 ≠ 全选（与订单域 filters.py 的守卫一致）
                return False
            # 业务语义：遍历全部选中标签，逐个判断是否存在「+ N」折叠标签
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

        ✅ **2026-10-23 真实页面实证有效**：把焦点落到
        `input.jx-select__input` 后按 ``Enter``，``aria-expanded`` 由
        ``false`` 变 ``true``、下拉浮层真的弹出（``ArrowDown`` 同样有效）。
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

        ⚠️ **点击 wrapper 是 toggle 语义**：浮层已经开着时再点一次会把它**关掉**。
        所以先做一次「浮层是否已经可见」的检测，已可见就直接复用，不再点击
        （2026-10-23 真实页面实测发现：上一轮残留的浮层会让层 A 点空）。

        全部失败时抛 RuntimeError，消息带阶段名 warehouse_scope_open_failed。
        """
        existing = await self._find_visible_overlay(page)
        if existing is not None:
            self._log(
                "[warehouse_filters] 仓库范围下拉已可见，直接复用（避免 toggle 关闭）"
            )
            return

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

    async def _find_visible_overlay(self, page: Any) -> Any | None:
        """浮层**当前是否已经可见**（不等待、不改变时序）。

        用于避免「点击 wrapper 把已开着的浮层 toggle 关闭」。
        """
        for locator in _scope_overlay_candidates(page, self.sel):
            if await _is_visible(locator):
                return locator
        return None

    def _scope_overlay_candidates(self, page: Any) -> list[Any]:
        """仓库范围下拉浮层的定位候选（见模块级同名说明）。"""
        return _scope_overlay_candidates(page, self.sel)

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
                    # 业务语义：同类关闭按钮取第一个匹配即可
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            try:
                # 固定等待：等弹层关闭动画结束再点下一个控件
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def _find_full_select_checkbox(self, overlay: Any) -> Any:
        """在浮层里找「全选」复选框（候选构造见模块级同名说明）。"""
        candidates = _full_select_checkbox_candidates(overlay, self.sel)
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

        if not await self._is_checkbox_selected(full_select):
            await full_select.click(timeout=self.sel.warehouse_scope_trigger_timeout_ms)

    async def _close_scope_dropdown(self, page: Any) -> None:
        """关闭仓库范围下拉浮层（按 ESC）。

        归档跑通脚本 `archive/export.py` 在勾完「全选」后就是用 ESC 收尾的：
        点「全选」**不会**自动收起下拉，必须显式关掉，否则浮层会盖住
        后续要点的「搜索」按钮。
        """
        try:
            await page.keyboard.press("Escape")
            # 固定等待：等下拉浮层的收起动画结束，避免盖住后续要点的按钮
            await page.wait_for_timeout(300)
        except Exception as e:
            self._log(f"[warehouse_filters] ESC 关闭下拉失败（已忽略）: {e}")

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
        """仓库范围筛选：pre-check → action → post-check。

        ⚠️ **「显式勾选全选」失败不阻断采集**（2026-10-23 真实页面实证）：
        仓库筛选是**可选**筛选项，**不选 = 全选**（空态与全选态的 SKU 总数、
        分页、表格内容完全一致），详见 `_apply_scope_all`。
        """
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
                    details={
                        "select_all": True,
                        "skipped": True,
                        "scope_all_selected": True,
                    },
                )

            # ── action + post-check：开下拉 + 勾「全选」 + 回读确认 ──
            details = await self._apply_scope_all(page)
            await self._close_scope_dropdown(page)
            await self._ensure_popup_closed(page)

            action_text = (
                "仓库范围已全选"
                if details.get("scope_all_selected")
                else "仓库范围：显式全选失败，已按默认范围（全部仓库）继续"
            )
            await self.report_step(
                "step_success", step_id="warehouse_scope_ready", action=action_text
            )
            return ResultBase(success=True, message="ok", details=details)
        except Exception as e:
            return await self._failure_result(page, e)

    async def _apply_scope_all(self, page: Any) -> dict[str, Any]:
        """执行「勾全选 + 回读确认」，失败**降级**而非抛错。

        降级依据：仓库筛选是可选筛选项，**不选 = 全选**（2026-10-23 实测，
        空态与全选态的 SKU 总数 / 分页 / 表格内容完全一致），且历史成功批次
        走的就是空态。显式全选失败只降级为告警 + 留痕，不拖垮整个导出任务。
        """
        try:
            await self._action_select_scope_all(page)
            await self._post_check_scope_all_selected(page)
        except Exception as e:
            self._log(
                "[warehouse_filters] 显式勾选「全选」失败，按默认范围"
                f"（空态=全部仓库）继续采集：{e}"
            )
            return {
                "select_all": True,
                "scope_all_selected": False,
                "scope_degraded_reason": str(e),
                "scope_degraded_note": (
                    "空态=全部仓库（2026-10-23 实测），显式全选失败不影响数据范围"
                ),
            }
        return {"select_all": True, "scope_all_selected": True}

    async def _failure_result(self, page: Any, exc: Exception) -> ResultBase:
        """失败路径：截图 + 阶段事件 + 失败结果。"""
        screenshot_path = await self._capture_failure_screenshot(
            page, "warehouse_scope"
        )
        message = str(exc)
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
