"""妙手仓库清单「更新时间维度 + 自定义区间」筛选组件（B1）。

为什么必须单独一个组件
----------------------
妙手的仓库清单页**默认不按时间筛选**，导出的是全量。
要做增量采集，必须在「搜索」之前把筛选器设成「更新时间维度 + 目标区间」，
否则采回来的还是全量 —— **看起来成功，实际白采**。

三处静默失败（实测：页面照常显示、不报错，只会安静地给错数据）
------------------------------------------------------------
| # | 失败 | 后果 |
|---|---|---|
| 1 | **维度没切**（默认是「创建时间」） | 同区间按更新时间 147 个 SKU，按创建时间只有 3 个 |
| 2 | **「确定」没点**（区间填了没提交） | 筛选器仍是旧值，导出范围完全不对 |
| 3 | **搜索没刷新** | 拿到的还是上一次的结果 |

→ 每一步都必须拿到**落地证据**，拿不到就当失败。
宁可失败，也不能拿错数据还显示成功。

三类落地证据（都可断言）
------------------------
1. **维度**：维度下拉的 ``modelvaluegroup`` 属性以 ``gmtModified`` 开头
2. **区间**：点完「确定」后，筛选器根的 ``modelvaluegroup`` 含目标起止时间
3. **结果**：点搜索后「SKU总数」**大于 0** 且**不超过**筛选前的总数

> 「确定」与「清空」长得几乎一样：``确定 = button.jx-picker-panel__link-btn.is-plain``、
> ``清空 = ...is-text``。**必须用完整 class 区分**，只匹配 ``is-plain`` 会误点「清空」，
> 把刚填好的区间清成空 —— 那是第三种静默失败。

本组件不含任何除法/判定逻辑，只负责「把筛选器设到指定状态 + 交出证据」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors

_DIGITS = re.compile(r"(\d[\d,]*)")


@dataclass(frozen=True)
class InventoryDateFilterEvidence:
    """一次筛选落地后可断言的证据。"""

    dimension: str
    """维度下拉上的 ``modelvaluegroup``，必须是 ``gmtModified…``"""

    applied_range: str
    """筛选器根上读回的已应用区间原文"""

    start: str
    end: str


class MiaoshouInventoryDateFilter:
    """把仓库清单的筛选器设成「更新时间维度 + 自定义区间」。"""

    platform = "miaoshou"
    component_type = "inventory_date_filter"
    data_domain = "inventory"

    def __init__(
        self, ctx: ExecutionContext, selectors: InventorySelectors | None = None
    ) -> None:
        self.ctx = ctx
        self.sel = selectors or InventorySelectors()

    # ------------------------------------------------------------------
    # 取值 / 断言
    # ------------------------------------------------------------------
    @staticmethod
    async def _read_attr(locator: Any, name: str) -> str:
        try:
            value = await locator.get_attribute(name)
        except Exception:
            return ""
        return str(value or "").strip()

    @staticmethod
    def _contains_time(applied: str, value: str) -> bool:
        """已应用区间里是否含目标时刻。

        只比对**日期部分**：妙手回填的文本格式（``2026-10-01 00:00:00`` /
        ``2026-10-01`` / 带逗号的千分位）实测不固定，比日期稳。
        """
        normalized = " ".join((applied or "").split())
        if not normalized:
            return False
        date_part = value.split(" ")[0]
        return bool(value and value in normalized) or bool(
            date_part and date_part in normalized
        )

    async def read_sku_total(self, page: Any) -> Optional[int]:
        """读页面上的「SKU总数」。读不到返回 None（**不等于 0**）。"""
        try:
            element = page.get_by_text(
                self.sel.inventory_date_filter_sku_total_text, exact=False
            ).first
            text = (await element.text_content()) or ""
            match = _DIGITS.search(text)
            if match:
                return int(match.group(1).replace(",", ""))
            # 数字可能在标签的兄弟节点上 → 再看一层父节点
            parent = element.locator("xpath=..")
            parent_text = (await parent.text_content()) or ""
            match = _DIGITS.search(parent_text)
            if match:
                return int(match.group(1).replace(",", ""))
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # 各步骤
    # ------------------------------------------------------------------
    async def _open_panel(self, page: Any) -> None:
        for selector in self.sel.inventory_date_filter_root_selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.click(timeout=1500)
                await self._wait_panel(page)
                return
            except Exception:
                continue
        for label in ("更新时间", "创建时间"):
            try:
                locator = page.get_by_text(label, exact=False).first
                await locator.click(timeout=1500)
                await self._wait_panel(page)
                return
            except Exception:
                continue
        raise RuntimeError("仓库清单日期筛选面板打不开")

    async def _wait_panel(self, page: Any) -> None:
        panel = page.locator(self.sel.inventory_date_filter_panel_selector).first
        await panel.wait_for(state="visible", timeout=5000)

    async def _dimension_select(self, page: Any) -> Any:
        select = page.locator(
            self.sel.inventory_date_filter_dimension_select_selector
        ).first
        await select.wait_for(state="visible", timeout=5000)
        return select

    async def _pick_dimension_option(self, page: Any, label: str) -> None:
        options = page.locator(self.sel.inventory_date_filter_dimension_option_selector)
        try:
            count = await options.count()
        except Exception:
            count = 0
        for index in range(count):
            option = options.nth(index)
            try:
                text = (await option.text_content()) or ""
            except Exception:
                continue
            if label in text:
                await option.click(timeout=1500)
                return
        raise RuntimeError(f"维度下拉里找不到「{label}」")

    async def _switch_to_modified_dimension(self, page: Any) -> str:
        """把维度切到「更新时间」，并断言落地证据。"""
        select = await self._dimension_select(page)
        current = await self._read_attr(
            select, self.sel.inventory_date_filter_value_attr
        )
        if not current.startswith(self.sel.inventory_date_filter_dimension_modified):
            try:
                await select.click(timeout=1500)
            except Exception:
                wrapper = page.locator(".jx-picker-panel .jx-select__wrapper").first
                await wrapper.click(timeout=1500)
            await self._pick_dimension_option(
                page, self.sel.inventory_date_filter_dimension_modified_label
            )

        for _ in range(10):
            value = await self._read_attr(
                select, self.sel.inventory_date_filter_value_attr
            )
            if value.startswith(self.sel.inventory_date_filter_dimension_modified):
                return value
            try:
                await page.wait_for_timeout(150)
            except Exception:
                continue
        raise RuntimeError(
            "维度未切到「更新时间」（modelvaluegroup 未以 gmtModified 开头）"
        )

    async def _fill_range(self, page: Any, *, start: str, end: str) -> None:
        inputs = page.locator(self.sel.inventory_date_filter_range_input_selector)
        try:
            count = await inputs.count()
        except Exception:
            count = 0
        if count < 2:
            raise RuntimeError(f"日期区间输入框不足两个（实际 {count} 个）")
        for index, value in ((0, start), (1, end)):
            field = inputs.nth(index)
            await field.click(timeout=1500)
            try:
                await field.press("Control+A")
            except Exception:
                pass
            await field.fill(value, timeout=1500)

    async def _click_confirm(self, page: Any) -> None:
        """点「确定」。

        选择器必须带完整 class（``is-plain``），否则会命中「清空」（``is-text``）——
        把刚填好的区间清成空，是第三种静默失败。
        """
        confirm = page.locator(self.sel.inventory_date_filter_confirm_selector).first
        await confirm.wait_for(state="visible", timeout=5000)
        await confirm.click(timeout=1500)

    async def _read_applied_range(self, page: Any) -> str:
        for selector in self.sel.inventory_date_filter_root_selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="attached", timeout=1500)
                value = await self._read_attr(
                    locator, self.sel.inventory_date_filter_value_attr
                )
                if value:
                    return value
            except Exception:
                continue
        return ""

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    async def assert_search_refreshed(
        self,
        page: Any,
        *,
        total_before: Optional[int],
        logger: Any = None,
    ) -> None:
        """搜索后断言结果集确实刷新了（读筛选后的总数并判定）。"""
        total_after = await self.read_sku_total(page)
        assert_search_results_refreshed(
            total_before=total_before, total_after=total_after, logger=logger
        )

    async def apply_incremental_range(
        self, page: Any, *, start: str, end: str
    ) -> InventoryDateFilterEvidence:
        """把筛选器设成「更新时间 + [start, end]」，并交出落地证据。

        ``start`` / ``end`` 用 ``YYYY-MM-DD HH:MM:SS`` 文本。
        """
        await self._open_panel(page)
        dimension = await self._switch_to_modified_dimension(page)
        await self._fill_range(page, start=start, end=end)
        await self._click_confirm(page)

        applied = ""
        for _ in range(10):
            applied = await self._read_applied_range(page)
            if (
                applied
                and self._contains_time(applied, start)
                and self._contains_time(applied, end)
            ):
                break
            try:
                await page.wait_for_timeout(150)
            except Exception:
                continue
        if not (
            self._contains_time(applied, start) and self._contains_time(applied, end)
        ):
            raise RuntimeError(
                f"区间未生效：期望含 {start} / {end}，实际读到 {applied!r}"
            )

        return InventoryDateFilterEvidence(
            dimension=dimension,
            applied_range=applied,
            start=start,
            end=end,
        )


# 增量区间在执行配置里的键名
INCREMENTAL_RANGE_CONFIG_KEY = "inventory_incremental_range"


def read_incremental_range(config: Any) -> Optional[tuple[str, str]]:
    """从执行配置里读增量区间；没配就是全量采集（返回 None）。

    约定：``config["inventory_incremental_range"] = {"start": "...", "end": "..."}``
    """
    if not isinstance(config, dict):
        return None
    payload = config.get(INCREMENTAL_RANGE_CONFIG_KEY)
    if not isinstance(payload, dict):
        return None
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return None
    return start, end


def assert_search_results_refreshed(
    *,
    total_before: Optional[int],
    total_after: Optional[int],
    logger: Any = None,
) -> None:
    """断言搜索确实刷新了结果集。

    - ``total_after`` 必须 **> 0**：0 = 筛选把范围清空了，或筛选根本没生效
    - ``total_after`` 不得 **> ``total_before``：筛选后不可能更多
    - 两者**相等**只记警告、不报错：增量窗口可能覆盖了全量数据（例如首采长窗口），
      此时相等是合法的。真正能抓住「维度切错 / 区间没生效」的是
      ``modelvaluegroup`` 那两条证据，不是这里的计数差。
    """
    if total_after is None:
        raise RuntimeError("读不到「SKU总数」：搜索结果没有刷新")
    if total_after <= 0:
        raise RuntimeError(
            f"「SKU总数」为 {total_after}：筛选把范围清空了，或筛选根本没生效"
        )
    if total_before is not None and total_after > total_before:
        raise RuntimeError(
            f"「SKU总数」筛选后反而变多（{total_before} → {total_after}）：筛选没生效"
        )
    if total_before is not None and total_after == total_before:
        message = (
            f"「SKU总数」筛选前后都是 {total_after}："
            "增量窗口可能覆盖了全量数据，请确认窗口区间"
        )
        if logger is not None:
            try:
                logger.warning(message)
            except Exception:
                pass
