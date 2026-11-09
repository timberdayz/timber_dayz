#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标管理数据同步服务（第三批-C：``a_class.sales_targets_a`` 已下线）

背景
----
``a_class.sales_targets_a`` 曾是「店铺月度目标」的**派生副本**：
它由本服务从 ``a_class.sales_targets``（父目标）+ ``a_class.target_breakdown``
（店铺分解）同步而来，读方有三个（两个 API 视图 + 看板服务）。

第三批-C 收敛后，**真 SSOT 就是 ``a_class.target_breakdown`` 本身**：

- 写入方：目标管理 / 目标工作台**直接**写 ``a_class.target_breakdown``；
- 删除方：目标行被删除时，分解行由外键 ``fk_target_breakdown_sales_targets``
  的 ``ON DELETE CASCADE`` 自动清理；
- 读方：两个 API 视图与看板服务**直接**读 ``a_class.target_breakdown``。

于是"再同步一份副本"这件事本身消失了。

本文件保留什么、为什么保留
------------------------
调用方（``backend/domains/business/routers/target_management.py``、
``backend/services/shop_target_workbench_service.py``）的调用签名与返回结构
**保持不变**，否则会牵动本轮范围外的文件：

- ``TargetSyncService.sync_target_to_a_class(target_id, commit)``
  → ``{"synced": n, "skipped": n, "errors": [...]}``
- ``TargetSyncService.delete_target_from_a_class(target_id, commit)``
  → ``{"deleted": n, "errors": [...]}``
- 模块级便捷函数 ``sync_target_after_create`` / ``sync_target_after_delete``

但**不再写任何投影表**：

- ``sync_target_to_a_class`` 现在只回报"该目标当前生效的店铺档位行数"
  （与旧实现的计数口径一致：旧实现每 upsert 一行有效店铺分解就 ``synced += 1``）；
- ``delete_target_from_a_class`` 不再删任何行 —— 分解行是 SSOT 本体，
  目标行删除时由外键级联清理；提前删掉反而会**丢历史分解**
  （例如目标工作台把旧月目标置为 inactive 时，分解必须留着）。

v4.21.0 引入，第三批-C 改为 SSOT 直读
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List

from modules.core.db import (
    SalesTarget,
    TargetBreakdown,
)
from modules.core.logger import get_logger
from backend.services.target_breakdown_selection import select_effective_shop_breakdowns

logger = get_logger(__name__)


class TargetSyncService:
    """目标 → 店铺分解（SSOT 直读）兼容外壳。

    ⚠️ 方法名里的 ``_a_class`` 是历史包袱：本服务**不再**与
    ``a_class.sales_targets_a`` 打交道。方法名保留是为了不牵动
    本轮范围外的调用方（目标管理、目标工作台）。
    """

    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db

    async def sync_target_to_a_class(self, target_id: int, commit: bool = True) -> Dict[str, Any]:
        """
        回报目标当前生效的「店铺 × 月」档位行数。

        第三批-C 起 ``a_class.target_breakdown`` 本身就是 SSOT，
        目标分解在写入时就已经落到位，**这里不再做投影写入**；
        只统计有效店铺分解行数，保持与旧实现一致的返回口径。

        Args:
            target_id: 目标ID

        Returns:
            同步结果 {synced: int, skipped: int, errors: list}
        """
        result: Dict[str, Any] = {
            "synced": 0,
            "skipped": 0,
            "errors": [],
        }

        try:
            target = (await self.db.execute(
                select(SalesTarget).where(SalesTarget.id == target_id)
            )).scalar_one_or_none()

            if not target:
                result["errors"].append(f"Target {target_id} not found")
                return result

            breakdown_rows = (await self.db.execute(
                select(TargetBreakdown).where(
                    TargetBreakdown.target_id == target_id,
                    TargetBreakdown.breakdown_type == "shop",
                )
            )).scalars().all()
            breakdowns = select_effective_shop_breakdowns(
                breakdown_rows,
                target.period_start,
                target.period_end,
            )

            if not breakdowns:
                logger.info(f"[TargetSync] Target {target_id} has no shop breakdowns, skipping")
                result["skipped"] = 1
                return result

            result["synced"] = len(breakdowns)
            logger.info(
                f"[TargetSync] Target {target_id} shop breakdown rows: {result['synced']}"
            )

            if commit:
                await self.db.commit()

        except Exception as e:
            if commit:
                await self.db.rollback()
            result["errors"].append(str(e))
            logger.error(f"[TargetSync] sync_target_to_a_class failed: {e}", exc_info=True)

        return result

    async def sync_all_active_targets(self) -> Dict[str, Any]:
        """
        批量回报所有活跃目标的店铺分解行数（第三批-C 后不再写投影表）。
        """
        result: Dict[str, Any] = {
            "total_targets": 0,
            "synced_targets": 0,
            "synced_records": 0,
            "errors": [],
        }

        try:
            targets = (await self.db.execute(
                select(SalesTarget).where(SalesTarget.status == "active")
            )).scalars().all()

            result["total_targets"] = len(targets)

            for target in targets:
                sync_result = await self.sync_target_to_a_class(target.id)
                if sync_result["synced"] > 0:
                    result["synced_targets"] += 1
                    result["synced_records"] += sync_result["synced"]
                result["errors"].extend(sync_result["errors"])

            logger.info(
                f"[TargetSync] Batch scan completed: {result['synced_targets']}/"
                f"{result['total_targets']} targets, "
                f"{result['synced_records']} shop breakdown rows"
            )

        except Exception as e:
            await self.db.rollback()
            result["errors"].append(str(e))
            logger.error(f"[TargetSync] sync_all_active_targets failed: {e}", exc_info=True)

        return result

    async def delete_target_from_a_class(self, target_id: int, commit: bool = True) -> Dict[str, Any]:
        """
        第三批-C 起**不需要**清理投影行。

        店铺分解行是 SSOT 本体（``a_class.target_breakdown``），目标行被删除时
        由外键 ``fk_target_breakdown_sales_targets`` 的 ``ON DELETE CASCADE``
        自动清理。这里只做一次**只读**核对，确认目标确实没有残留分解行，
        并保持旧版的返回结构 ``{"deleted": int, "errors": list}``。

        ⚠️ 绝不能在这里主动删分解行：目标工作台把旧月目标置为 inactive 时
        仍需要保留它的分解（历史快照），提前删会丢数据。

        Args:
            target_id: 目标ID

        Returns:
            清理结果 {deleted: int, errors: list}
        """
        result: Dict[str, Any] = {
            "deleted": 0,
            "errors": [],
        }

        try:
            remaining = (await self.db.execute(
                select(TargetBreakdown.id).where(
                    TargetBreakdown.target_id == target_id,
                )
            )).scalars().all()

            if remaining:
                logger.info(
                    f"[TargetSync] Target {target_id} still owns {len(remaining)} "
                    f"breakdown rows; they are removed by FK cascade on target delete."
                )

            if commit:
                await self.db.commit()

        except Exception as e:
            if commit:
                await self.db.rollback()
            result["errors"].append(str(e))
            logger.error(f"[TargetSync] delete_target_from_a_class failed: {e}", exc_info=True)

        return result

    def _calculate_year_month(self, period_start: date, period_end: date) -> str:
        """
        从目标周期计算 year_month

        规则：取 period_start 的年月
        """
        if period_start:
            return period_start.strftime('%Y-%m')
        return datetime.now(timezone.utc).strftime('%Y-%m')

    @staticmethod
    def _normalize_platform_code(platform_code: Optional[str]) -> str:
        value = str(platform_code or "").strip().lower()
        if not value or value in {"none", "null"}:
            return "unknown"
        return value


async def sync_target_after_create(db: AsyncSession, target_id: int) -> Dict[str, Any]:
    """
    创建/更新目标或分解后触发同步（便捷函数）

    第三批-C 起：真 SSOT 已被直接写入，本函数只回报分解行数。
    """
    service = TargetSyncService(db)
    return await service.sync_target_to_a_class(target_id)


async def sync_target_after_delete(db: AsyncSession, target_id: int) -> Dict[str, Any]:
    """
    删除目标前触发清理（便捷函数）

    第三批-C 起：分解行由外键级联清理，这里只做只读核对。
    """
    service = TargetSyncService(db)
    return await service.delete_target_from_a_class(target_id)
