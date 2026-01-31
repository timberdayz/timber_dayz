#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标管理数据同步服务

功能：
- 将 sales_targets + target_breakdown 数据同步到 a_class.sales_targets_a
- 确保经营指标SQL和前端目标管理使用的是同一份数据

数据流：
- 前端目标管理 → sales_targets + target_breakdown (public schema)
- 同步服务 → a_class.sales_targets_a
- 经营指标SQL → 读取 a_class.sales_targets_a

v4.21.0新增
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from typing import Optional, Dict, Any, List

from modules.core.db import (
    SalesTarget,
    TargetBreakdown,
    SalesTargetA,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


class TargetSyncService:
    """目标管理数据同步服务"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
    
    async def sync_target_to_a_class(self, target_id: int) -> Dict[str, Any]:
        """
        将单个目标的分解数据同步到 a_class.sales_targets_a
        
        逻辑：
        1. 获取目标和店铺分解数据
        2. 按 shop_id + year_month 聚合
        3. Upsert 到 a_class.sales_targets_a
        
        Args:
            target_id: 目标ID
            
        Returns:
            同步结果 {synced: int, errors: list}
        """
        result = {
            "synced": 0,
            "skipped": 0,
            "errors": []
        }
        
        try:
            # 1. 获取目标
            target = (await self.db.execute(
                select(SalesTarget).where(SalesTarget.id == target_id)
            )).scalar_one_or_none()
            
            if not target:
                result["errors"].append(f"Target {target_id} not found")
                return result
            
            # 2. 获取按店铺分解的数据
            breakdowns = (await self.db.execute(
                select(TargetBreakdown).where(
                    TargetBreakdown.target_id == target_id,
                    TargetBreakdown.breakdown_type == "shop"
                )
            )).scalars().all()
            
            if not breakdowns:
                logger.info(f"[TargetSync] Target {target_id} has no shop breakdowns, skipping")
                result["skipped"] = 1
                return result
            
            # 3. 计算 year_month（从目标周期计算）
            year_month = self._calculate_year_month(target.period_start, target.period_end)
            
            # 4. 按 shop_id 聚合并同步
            for breakdown in breakdowns:
                if not breakdown.shop_id:
                    continue
                    
                try:
                    await self._upsert_sales_target_a(
                        shop_id=breakdown.shop_id,
                        year_month=year_month,
                        target_sales_amount=breakdown.target_amount or 0.0,
                        target_quantity=breakdown.target_quantity or 0
                    )
                    result["synced"] += 1
                    logger.debug(f"[TargetSync] Synced: shop_id={breakdown.shop_id}, year_month={year_month}")
                except Exception as e:
                    result["errors"].append(f"Failed to sync shop {breakdown.shop_id}: {str(e)}")
                    logger.error(f"[TargetSync] Failed to sync breakdown: {e}", exc_info=True)
            
            await self.db.commit()
            logger.info(f"[TargetSync] Target {target_id} synced: {result['synced']} records")
            
        except Exception as e:
            await self.db.rollback()
            result["errors"].append(str(e))
            logger.error(f"[TargetSync] sync_target_to_a_class failed: {e}", exc_info=True)
        
        return result
    
    async def sync_all_active_targets(self) -> Dict[str, Any]:
        """
        同步所有活跃目标到 a_class.sales_targets_a
        
        Returns:
            同步结果统计
        """
        result = {
            "total_targets": 0,
            "synced_targets": 0,
            "synced_records": 0,
            "errors": []
        }
        
        try:
            # 获取所有活跃目标
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
            
            logger.info(f"[TargetSync] Batch sync completed: {result['synced_targets']}/{result['total_targets']} targets, {result['synced_records']} records")
            
        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"[TargetSync] sync_all_active_targets failed: {e}", exc_info=True)
        
        return result
    
    async def delete_target_from_a_class(self, target_id: int) -> Dict[str, Any]:
        """
        删除目标时，清理 a_class.sales_targets_a 中对应的数据
        
        注意：由于 a_class.sales_targets_a 是按 shop_id + year_month 聚合的，
        需要检查是否有其他目标也指向同一 shop_id + year_month，
        如果没有才删除。
        
        Args:
            target_id: 目标ID
            
        Returns:
            删除结果
        """
        result = {
            "deleted": 0,
            "errors": []
        }
        
        try:
            # 获取目标
            target = (await self.db.execute(
                select(SalesTarget).where(SalesTarget.id == target_id)
            )).scalar_one_or_none()
            
            if not target:
                return result
            
            # 获取分解数据
            breakdowns = (await self.db.execute(
                select(TargetBreakdown).where(
                    TargetBreakdown.target_id == target_id,
                    TargetBreakdown.breakdown_type == "shop"
                )
            )).scalars().all()
            
            year_month = self._calculate_year_month(target.period_start, target.period_end)
            
            for breakdown in breakdowns:
                if not breakdown.shop_id:
                    continue
                
                # 检查是否有其他目标指向同一 shop_id + year_month
                other_targets = await self._count_other_targets_for_shop_month(
                    target_id=target_id,
                    shop_id=breakdown.shop_id,
                    year_month=year_month
                )
                
                if other_targets == 0:
                    # 没有其他目标，可以删除（使用中文字段名）
                    await self.db.execute(
                        text("""
                            DELETE FROM a_class.sales_targets_a 
                            WHERE "店铺ID" = :shop_id AND "年月" = :year_month
                        """),
                        {"shop_id": breakdown.shop_id, "year_month": year_month}
                    )
                    result["deleted"] += 1
            
            await self.db.commit()
            logger.info(f"[TargetSync] Target {target_id} cleanup: {result['deleted']} records deleted from a_class")
            
        except Exception as e:
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
        return datetime.utcnow().strftime('%Y-%m')
    
    async def _upsert_sales_target_a(
        self,
        shop_id: str,
        year_month: str,
        target_sales_amount: float,
        target_quantity: int
    ):
        """
        Upsert 到 a_class.sales_targets_a
        
        使用原生SQL执行 upsert，因为 ORM 可能不支持跨 schema 的 upsert
        注意：表使用中文字段名
        """
        await self.db.execute(
            text("""
                INSERT INTO a_class.sales_targets_a 
                    ("店铺ID", "年月", "目标销售额", "目标订单数", "创建时间", "更新时间")
                VALUES 
                    (:shop_id, :year_month, :target_sales_amount, :target_quantity, NOW(), NOW())
                ON CONFLICT ("店铺ID", "年月") 
                DO UPDATE SET 
                    "目标销售额" = EXCLUDED."目标销售额",
                    "目标订单数" = EXCLUDED."目标订单数",
                    "更新时间" = NOW()
            """),
            {
                "shop_id": shop_id,
                "year_month": year_month,
                "target_sales_amount": target_sales_amount,
                "target_quantity": target_quantity
            }
        )
    
    async def _count_other_targets_for_shop_month(
        self,
        target_id: int,
        shop_id: str,
        year_month: str
    ) -> int:
        """
        统计其他目标中指向同一 shop_id + year_month 的数量
        """
        # 解析 year_month 为日期范围
        year, month = year_month.split('-')
        period_start = date(int(year), int(month), 1)
        
        result = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT t.id)
                FROM a_class.sales_targets t
                JOIN a_class.target_breakdown tb ON tb.target_id = t.id
                WHERE t.id != :target_id
                  AND t.status = 'active'
                  AND tb.breakdown_type = 'shop'
                  AND tb.shop_id = :shop_id
                  AND DATE_TRUNC('month', t.period_start) = DATE_TRUNC('month', :period_start::date)
            """),
            {
                "target_id": target_id,
                "shop_id": shop_id,
                "period_start": period_start.isoformat()
            }
        )
        return result.scalar() or 0


async def sync_target_after_create(db: AsyncSession, target_id: int) -> Dict[str, Any]:
    """
    创建目标后触发同步（便捷函数）
    
    在 target_management.py 的 create_target 和 create_breakdown 中调用
    """
    service = TargetSyncService(db)
    return await service.sync_target_to_a_class(target_id)


async def sync_target_after_delete(db: AsyncSession, target_id: int) -> Dict[str, Any]:
    """
    删除目标前触发清理（便捷函数）
    
    在 target_management.py 的 delete_target 中调用
    """
    service = TargetSyncService(db)
    return await service.delete_target_from_a_class(target_id)
