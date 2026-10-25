"""妙手仓库清单的增量采集编排（B1）。

为什么单独一个 mixin
--------------------
主导出类 ``MiaoshouInventoryExport`` 已经接近「类 ≤500 行」的硬门禁，
而增量编排是**独立关注点**（切维度 → 填区间 → 断言结果集刷新），
拆出去各自都好读，也让主导出类守住门禁。

依赖宿主类提供：``ctx`` / ``sel`` / ``date_filter_component`` /
``_stage_error`` / ``report_step`` / ``logger``。
"""

from __future__ import annotations

from typing import Any

from modules.platforms.miaoshou.components.inventory_date_filter import (
    read_incremental_range,
)

# 步骤日志用的定位信号名
SIGNAL_DATE_FILTER = "date_filter:dimension_text"
SIGNAL_SEARCH_BUTTON = "role:button:搜索"


class MiaoshouInventoryIncrementalMixin:
    """增量采集编排：搜索前设好筛选器，搜索后断言结果集确实刷新了。

    没配置增量区间 → 整段流程跳过（**全量采集场景行为不变**）。

    顺序（增量模式）
    ----------------
    1. 全选仓库
    2. **搜索 #1** → 读到「SKU总数」当**基线**（筛选前的全量口径）
    3. 设「更新时间维度 + 目标区间」
    4. **搜索 #2** → 让筛选生效，再读一次「SKU总数」
    5. 断言：筛选后总数不得超过基线

    为什么必须多搜索一次
    --------------------
    仓库范围和日期区间是**两套独立筛选条件**：仓库选完不点搜索，页面上显示的
    还是上一次的搜索结果。基线必须是「仓库已全选、时间未筛选」这个真实口径，
    否则拿到的基线不准，筛选是否生效的断言就是假的。
    """

    STAGE_DATE_FILTER_READY = "date_filter_ready"

    # 筛选**之前**的「SKU总数」基线：搜索 #1 之后读，用来断言筛选是否生效
    _sku_total_before: int | None = None

    def _incremental_enabled(self) -> bool:
        """这次采集是不是增量模式（执行配置里带了增量区间）。"""
        return read_incremental_range(self.ctx.config) is not None

    async def _capture_baseline_total(self, page: Any) -> None:
        """搜索 #1 之后读「SKU总数」当基线。"""
        if not self._incremental_enabled():
            return
        self._sku_total_before = await self.date_filter_component.read_sku_total(page)

    async def _apply_incremental_date_filter(self, page: Any) -> None:
        """把筛选器设成「更新时间维度 + 目标区间」，并交出可断言的落地证据。"""
        window = read_incremental_range(self.ctx.config)
        if window is None:
            return

        self._current_stage = self.STAGE_DATE_FILTER_READY
        await self.report_step(
            "step_start",
            step_id=self.STAGE_DATE_FILTER_READY,
            action="设置更新时间维度与采集区间",
        )
        try:
            evidence = await self.date_filter_component.apply_incremental_range(
                page, start=window[0], end=window[1]
            )
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="date_filter_failed",
                stage=self.STAGE_DATE_FILTER_READY,
                reason=str(e),
                matched_signal=SIGNAL_DATE_FILTER,
            )
            raise error from e

        await self.report_step(
            "step_success",
            step_id=self.STAGE_DATE_FILTER_READY,
            action=f"筛选已生效（维度 {evidence.dimension}）",
        )

    async def _assert_search_refreshed(self, page: Any) -> None:
        """搜索 #2 之后断言结果集确实按筛选收窄了（只在增量模式断言）。"""
        if self._sku_total_before is None:
            return
        try:
            await self.date_filter_component.assert_search_refreshed(
                page, total_before=self._sku_total_before, logger=self.logger
            )
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="search_failed",
                stage=self.STAGE_SEARCH_RESULTS_READY,
                reason=str(e),
                matched_signal=SIGNAL_SEARCH_BUTTON,
            )
            raise error from e
