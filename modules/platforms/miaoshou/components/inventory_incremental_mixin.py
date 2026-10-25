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
SIGNAL_DATE_FILTER = "date_filter:modelvaluegroup"
SIGNAL_SEARCH_BUTTON = "role:button:搜索"


class MiaoshouInventoryIncrementalMixin:
    """增量采集编排：搜索前设好筛选器，搜索后断言结果集确实刷新了。

    没配置增量区间 → 整段流程跳过（**全量采集场景行为不变**）。
    """

    STAGE_DATE_FILTER_READY = "date_filter_ready"

    # 筛选**之前**的「SKU总数」：搜索后拿它断言结果集确实刷新了
    _sku_total_before: int | None = None

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
            self._sku_total_before = await self.date_filter_component.read_sku_total(
                page
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
        """搜索后断言结果集刷新了（只在增量模式下断言）。"""
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
