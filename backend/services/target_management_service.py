#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标管理服务

负责目标管理的达成率计算逻辑（C类数据）
从路由层提取业务逻辑，符合分层架构规范
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import date, datetime
from typing import Dict, Any, Optional

from modules.core.db import (
    SalesTarget,
    TargetBreakdown,
    FactOrder
)
from backend.services.c_class_data_service import CClassDataService
from modules.core.logger import get_logger

logger = get_logger(__name__)


class TargetManagementService:
    """目标管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_target_achievement(self, target_id: int) -> Dict[str, Any]:
        """
        计算目标达成情况（C类数据：系统自动计算）
        
        从fact_orders表聚合计算实际销售额和订单数
        更新目标和分解的达成数据
        
        Args:
            target_id: 目标ID
            
        Returns:
            计算结果的字典，包含目标信息和分解信息
        """
        # 查询目标
        target = self.db.execute(
            select(SalesTarget).where(SalesTarget.id == target_id)
        ).scalar_one_or_none()
        
        if not target:
            raise ValueError(f"目标不存在: {target_id}")
        
        # 查询分解列表
        breakdowns = self.db.execute(
            select(TargetBreakdown).where(
                TargetBreakdown.target_id == target_id
            )
        ).scalars().all()
        
        total_achieved_amount = 0.0
        total_achieved_quantity = 0
        
        # 使用C类数据查询服务优化数据查询（保留业务逻辑）
        c_class_service = CClassDataService(self.db)
        
        # 计算每个分解的达成情况
        for breakdown in breakdowns:
            if breakdown.breakdown_type == "shop":
                # 店铺分解：使用CClassDataService查询销售数据
                if breakdown.platform_code and breakdown.shop_id:
                    sales_data = c_class_service.query_shop_sales_by_period(
                        start_date=target.period_start,
                        end_date=target.period_end,
                        platform_code=breakdown.platform_code,
                        shop_id=breakdown.shop_id
                    )
                    
                    # 获取单个店铺的数据
                    if sales_data["shops"]:
                        shop_data = sales_data["shops"][0]
                        breakdown.achieved_amount = shop_data["amount"]
                        breakdown.achieved_quantity = shop_data["orders"]
                    else:
                        breakdown.achieved_amount = 0.0
                        breakdown.achieved_quantity = 0
                    
                    breakdown.achievement_rate = (
                        (breakdown.achieved_amount / breakdown.target_amount * 100) if breakdown.target_amount > 0 else 0.0
                    )
                    
                    total_achieved_amount += breakdown.achieved_amount
                    total_achieved_quantity += breakdown.achieved_quantity
            
            elif breakdown.breakdown_type == "time":
                # 时间分解：使用CClassDataService查询销售数据（所有店铺）
                if breakdown.period_start and breakdown.period_end:
                    sales_data = c_class_service.query_shop_sales_by_period(
                        start_date=breakdown.period_start,
                        end_date=breakdown.period_end,
                        platform_codes=None,  # 查询所有平台
                        shop_ids=None  # 查询所有店铺
                    )
                    
                    breakdown.achieved_amount = sales_data["total_amount"]
                    breakdown.achieved_quantity = sales_data["total_orders"]
                    breakdown.achievement_rate = (
                        (breakdown.achieved_amount / breakdown.target_amount * 100) if breakdown.target_amount > 0 else 0.0
                    )
                    
                    total_achieved_amount += breakdown.achieved_amount
                    total_achieved_quantity += breakdown.achieved_quantity
        
        # 如果没有分解，直接计算目标总体达成情况（使用CClassDataService）
        if not breakdowns:
            sales_data = c_class_service.query_shop_sales_by_period(
                start_date=target.period_start,
                end_date=target.period_end,
                platform_codes=None,  # 查询所有平台
                shop_ids=None  # 查询所有店铺
            )
            
            total_achieved_amount = sales_data["total_amount"]
            total_achieved_quantity = sales_data["total_orders"]
        
        # 更新目标总体达成情况
        target.achieved_amount = total_achieved_amount
        target.achieved_quantity = total_achieved_quantity
        target.achievement_rate = (
            (total_achieved_amount / target.target_amount * 100) if target.target_amount > 0 else 0.0
        )
        
        target.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(target)
        
        return {
            "target": target,
            "breakdowns": breakdowns,
            "total_achieved_amount": total_achieved_amount,
            "total_achieved_quantity": total_achieved_quantity,
            "achievement_rate": target.achievement_rate
        }
    
    def calculate_all_targets(self) -> Dict[str, Any]:
        """
        批量计算所有目标的达成情况
        
        Returns:
            计算结果统计
        """
        targets = self.db.execute(
            select(SalesTarget).where(
                SalesTarget.status.in_(["pending", "active"])
            )
        ).scalars().all()
        
        results = []
        success_count = 0
        failed_count = 0
        
        for target in targets:
            try:
                result = self.calculate_target_achievement(target.id)
                results.append({
                    "target_id": target.id,
                    "target_name": target.target_name,
                    "achievement_rate": result["achievement_rate"],
                    "status": "success"
                })
                success_count += 1
            except Exception as e:
                logger.error(f"计算目标{target.id}达成情况失败: {e}", exc_info=True)
                results.append({
                    "target_id": target.id,
                    "target_name": target.target_name,
                    "status": "failed",
                    "error": str(e)
                })
                failed_count += 1
        
        return {
            "total": len(targets),
            "success": success_count,
            "failed": failed_count,
            "results": results
        }

