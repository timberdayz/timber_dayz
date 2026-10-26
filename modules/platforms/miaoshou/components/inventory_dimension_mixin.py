"""妙手仓库清单「时间维度下拉」的操作（B1）。

为什么单独一个 mixin
--------------------
主组件类 ``MiaoshouInventoryDateFilter`` 已经接近「类 ≤500 行」的硬门禁，
而**维度下拉**是独立关注点（定位触发器 → 打开浮层 → 点「更新时间」→ 验证落地），
拆出去各自都好读，也让主组件守住门禁。
（与 ``inventory_incremental_mixin.py`` 同一个理由。）

2026-10-26 第二次失败现场（任务 5526faf9）留下的硬约束
---------------------------------------------------
真实页面上「创建时间 / 更新时间」**同时出现在两处**：

1. 筛选栏的维度下拉浮层里（``li.jx-select-dropdown__item``）
2. **结果表格的表头里**（``<div class="cell">更新时间</div>``，可排序）

``page.get_by_text("更新时间", exact=True)`` 的第一个命中是**表头**。
点它 → 触发表格排序 → 维度根本没切 → 报「维度未切到「更新时间」」。

→ 所以这里**所有定位都限定范围**：
- 触发器：``[modelvaluegroup*='gmt']``（维度键挂在触发器根上，表头没有）
- 选项：**可见的下拉浮层容器内**（表头不在浮层里）
- 读当前维度：**只从触发器读**（表头不算）

依赖宿主类提供：``sel``（``InventorySelectors``）。
"""

from __future__ import annotations

from typing import Any, Optional

# 维度下拉的两个选项文案（既是触发器上的当前值，也是浮层里的选项）
DIMENSION_CREATE = "创建时间"
DIMENSION_MODIFIED = "更新时间"


class InventoryDimensionMixin:
    """时间维度下拉的定位与切换（只管「维度」，不管日期区间）。"""

    # ------------------------------------------------------------------
    # 定位
    # ------------------------------------------------------------------
    async def _dimension_select(self, page: Any) -> Optional[Any]:
        """定位时间维度下拉的**触发器根**（带 gmt 维度键的 select）。

        真实页面结构（2026-10-26 取证）：
            <div class="jx-select jx-select--small pro-select"
                 fieldtype="select" modelvaluegroup="gmtCreate,">
              <div class="jx-select__wrapper jx-tooltip__trigger">
                <div class="jx-select__selected-item jx-select__placeholder">
                  <span>创建时间</span>

        维度键就挂在触发器根的 ``modelvaluegroup`` 上（gmtCreate / gmtModified），
        用它定位既能拿到触发器，又能天然排除表格表头（表头没有这个属性）。
        """
        try:
            locator = page.locator(
                self.sel.inventory_date_filter_dimension_select_selector
            )
            count = await locator.count()
        except Exception:
            return None
        for index in range(min(count, 6)):
            node = locator.nth(index)
            try:
                if not await node.is_visible():
                    continue
                key = await self._read_attr(
                    node, self.sel.inventory_date_filter_value_attr
                )
            except Exception:
                continue
            if key.strip().lower().startswith("gmt"):
                return node
        return None

    async def _dimension_of(self, trigger: Any) -> str:
        """读触发器上当前显示的维度（'创建时间' / '更新时间'）。

        优先读维度键（``modelvaluegroup``），读不到再读触发器里的文案。
        """
        try:
            key = (
                (
                    await self._read_attr(
                        trigger, self.sel.inventory_date_filter_value_attr
                    )
                )
                .strip()
                .lower()
            )
        except Exception:
            key = ""
        if self.sel.inventory_date_filter_dimension_modified.lower() in key:
            return DIMENSION_MODIFIED
        if self.sel.inventory_date_filter_dimension_create.lower() in key:
            return DIMENSION_CREATE
        try:
            text = ((await trigger.text_content()) or "").strip()
        except Exception:
            text = ""
        if DIMENSION_MODIFIED in text:
            return DIMENSION_MODIFIED
        if DIMENSION_CREATE in text:
            return DIMENSION_CREATE
        return ""

    async def read_current_dimension(self, page: Any) -> str:
        """读筛选栏上**当前显示**的维度文案（'创建时间' / '更新时间'）。

        只从**触发器**上读 —— 表格表头里也有同名的两列，
        全页读会把表头算进来，判定就废了（2026-10-26 真实失败）。
        """
        trigger = await self._dimension_select(page)
        if trigger is None:
            return ""
        return await self._dimension_of(trigger)

    # ------------------------------------------------------------------
    # 切换
    # ------------------------------------------------------------------
    async def _open_dimension_dropdown(self, page: Any, trigger: Any) -> None:
        """点开时间维度下拉（点触发器里的 wrapper 外壳）。"""
        try:
            wrapper = trigger.locator(
                self.sel.inventory_date_filter_dimension_wrapper_selector
            ).first
            await wrapper.click(timeout=2000)
            return
        except Exception:
            pass
        await trigger.click(timeout=2000)

    async def _find_dimension_option(self, page: Any) -> Optional[Any]:
        """在**可见的下拉浮层容器内**找「更新时间」选项。

        关键：范围限定在浮层里。表格表头里也有「更新时间」，
        全页找会点到表头去排序 —— 维度根本没切（2026-10-26 任务 5526faf9）。

        ⚠️ 真实页面上有**十几个** ``.jx-select-dropdown``（每个 select 一个），
        维度那个排在 DOM 靠后位置 → 先用 ``:visible`` 精准命中，
        别指望按顺序扫到它。
        """
        for selector in self.sel.inventory_date_filter_dropdown_container_selectors:
            for scoped in (f"{selector}:visible", selector):
                option = await self._option_in_containers(page, scoped)
                if option is not None:
                    return option
        return None

    async def _option_in_containers(self, page: Any, selector: str) -> Optional[Any]:
        """在一个容器选择器下找「更新时间」选项。"""
        try:
            containers = page.locator(selector)
            count = await containers.count()
        except Exception:
            return None
        for index in range(min(count, 24)):
            container = containers.nth(index)
            try:
                if not await container.is_visible():
                    continue
            except Exception:
                continue
            option = await self._first_option_in(container)
            if option is not None:
                return option
        return None

    async def _first_option_in(self, container: Any) -> Optional[Any]:
        """在浮层容器里找文案精确等于「更新时间」的选项。"""
        for selector in self.sel.inventory_date_filter_dimension_option_selectors:
            try:
                options = container.locator(selector)
                count = await options.count()
            except Exception:
                continue
            for index in range(min(count, 8)):
                option = options.nth(index)
                try:
                    if not await option.is_visible():
                        continue
                    text = ((await option.text_content()) or "").strip()
                except Exception:
                    continue
                if text == DIMENSION_MODIFIED:
                    return option
        return None

    async def _wait_dimension_option(self, page: Any) -> Any:
        """等浮层展开 —— 判据是浮层里出现可见的「更新时间」选项。"""
        for _ in range(20):
            option = await self._find_dimension_option(page)
            if option is not None:
                return option
            await self._settle(page)
        raise RuntimeError("时间维度下拉没有展开（浮层里找不到「更新时间」选项）")

    async def _switch_to_modified_dimension(self, page: Any) -> str:
        """把维度切到「更新时间」，并断言落地证据。"""
        trigger = await self._dimension_select(page)
        if trigger is None:
            raise RuntimeError(
                "找不到时间维度下拉触发器（页面上没有带 gmt 维度键的 select）"
            )
        current = await self._dimension_of(trigger)
        if current == DIMENSION_MODIFIED:
            # 幂等：已经是「更新时间」→ 不碰下拉（用户可能已手动选过）
            return current
        if not current:
            raise RuntimeError(
                "读不到时间维度的当前值：触发器上既没有「创建时间」也没有「更新时间」"
            )

        # 顺序无关：浮层**已经开着**就别再点触发器 —— 再点一下反而把它关了
        option = await self._find_dimension_option(page)
        if option is None:
            await self._open_dimension_dropdown(page, trigger)
            option = await self._wait_dimension_option(page)
        await option.click(timeout=2000)

        for _ in range(12):
            value = await self._dimension_of(trigger)
            if value == DIMENSION_MODIFIED:
                return value
            await self._settle(page)
        raise RuntimeError("维度未切到「更新时间」（下拉触发器上的文案没变）")
