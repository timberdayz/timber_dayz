#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
滞销清理排名服务（v4.11.0新增）

功能：
1. 计算店铺滞销清理排名
2. 计算清理金额和数量
3. 计算激励金额

滞销定义：
- 库存周转率低于8次/年
- 或库存天数超过45天
- 或产品状态为"滞销"

清理定义：
- 通过促销、清仓等方式销售滞销产品
- 记录清理金额和数量
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta

from modules.core.db import (
    ClearanceRanking,
    FactOrder,
    FactProductMetric,
    DimShop
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ClearanceRankingService:
    """滞销清理排名服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_clearance_ranking(
        self,
        metric_date: date,
        granularity: str = "monthly"
    ) -> Dict[str, Any]:
        """
        计算滞销清理排名
        
        参数：
            metric_date: 指标日期
            granularity: 粒度（monthly/weekly）
        
        返回：
            {
                "rankings": [
                    {
                        "rank": 1,
                        "platform_code": "Shopee",
                        "shop_id": "shop_001",
                        "shop_name": "Shopee新加坡旗舰店",
                        "clearance_amount": 125000.00,
                        "clearance_quantity": 250,
                        "incentive_amount": 1250.00
                    },
                    ...
                ],
                "total_shops": 10
            }
        """
        try:
            # 计算时间范围
            if granularity == "monthly":
                start_date = metric_date.replace(day=1)
                if start_date.month == 12:
                    end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
            elif granularity == "weekly":
                days_since_monday = metric_date.weekday()
                start_date = metric_date - timedelta(days=days_since_monday)
                end_date = start_date + timedelta(days=6)
            else:
                start_date = metric_date
                end_date = metric_date
            
            # 获取所有店铺
            shops = self.db.execute(select(DimShop)).scalars().all()
            
            rankings = []
            
            for shop in shops:
                # 计算店铺的清理数据
                clearance_data = self._calculate_shop_clearance(
                    shop.platform_code,
                    shop.shop_id,
                    start_date,
                    end_date
                )
                
                if clearance_data["clearance_amount"] > 0:
                    # 计算激励金额（清理金额的1%）
                    incentive_amount = clearance_data["clearance_amount"] * 0.01
                    
                    # 保存或更新排名记录
                    existing_ranking = self.db.execute(
                        select(ClearanceRanking).where(
                            ClearanceRanking.platform_code == shop.platform_code,
                            ClearanceRanking.shop_id == shop.shop_id,
                            ClearanceRanking.metric_date == metric_date,
                            ClearanceRanking.granularity == granularity
                        )
                    ).scalar_one_or_none()
                    
                    if existing_ranking:
                        existing_ranking.clearance_amount = clearance_data["clearance_amount"]
                        existing_ranking.clearance_quantity = clearance_data["clearance_quantity"]
                        existing_ranking.incentive_amount = incentive_amount
                        existing_ranking.total_incentive = incentive_amount
                        ranking = existing_ranking
                    else:
                        ranking = ClearanceRanking(
                            platform_code=shop.platform_code,
                            shop_id=shop.shop_id,
                            metric_date=metric_date,
                            granularity=granularity,
                            clearance_amount=clearance_data["clearance_amount"],
                            clearance_quantity=clearance_data["clearance_quantity"],
                            incentive_amount=incentive_amount,
                            total_incentive=incentive_amount
                        )
                        self.db.add(ranking)
                    
                    rankings.append({
                        "platform_code": shop.platform_code,
                        "shop_id": shop.shop_id,
                        "shop_name": shop.shop_name,
                        "clearance_amount": clearance_data["clearance_amount"],
                        "clearance_quantity": clearance_data["clearance_quantity"],
                        "incentive_amount": incentive_amount
                    })
            
            # 按清理金额排序
            rankings.sort(key=lambda x: x["clearance_amount"], reverse=True)
            
            # 更新排名
            for rank, ranking_data in enumerate(rankings, start=1):
                ranking_record = self.db.execute(
                    select(ClearanceRanking).where(
                        ClearanceRanking.platform_code == ranking_data["platform_code"],
                        ClearanceRanking.shop_id == ranking_data["shop_id"],
                        ClearanceRanking.metric_date == metric_date,
                        ClearanceRanking.granularity == granularity
                    )
                ).scalar_one_or_none()
                
                if ranking_record:
                    ranking_record.rank = rank
            
            self.db.commit()
            
            return {
                "rankings": rankings[:5],  # 只返回前5名
                "total_shops": len(rankings)
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"计算滞销清理排名失败: {e}", exc_info=True)
            raise
    
    def _calculate_shop_clearance(
        self,
        platform_code: str,
        shop_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        计算店铺的清理数据
        
        清理定义：
        - 销售价格低于成本价的产品（清仓）
        - 或通过促销活动销售的产品（促销）
        - 或库存天数超过45天的产品（滞销清理）
        """
        # TODO: 需要根据实际业务逻辑实现
        # 临时实现：从fact_orders查询低价订单（假设低于平均订单金额50%的为清理订单）
        
        # 计算平均订单金额
        avg_order_result = self.db.execute(
            select(
                func.avg(FactOrder.total_amount_rmb).label("avg_amount")
            ).where(
                FactOrder.platform_code == platform_code,
                FactOrder.shop_id == shop_id,
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            )
        ).first()
        
        avg_order_amount = float(avg_order_result.avg_amount or 0)
        clearance_threshold = avg_order_amount * 0.5  # 低于平均订单金额50%的视为清理订单
        
        # 查询清理订单
        clearance_result = self.db.execute(
            select(
                func.coalesce(func.sum(FactOrder.total_amount_rmb), 0).label("amount"),
                func.count(FactOrder.order_id).label("quantity")
            ).where(
                FactOrder.platform_code == platform_code,
                FactOrder.shop_id == shop_id,
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"]),
                FactOrder.total_amount_rmb <= clearance_threshold
            )
        ).first()
        
        clearance_amount = float(clearance_result.amount or 0)
        clearance_quantity = int(clearance_result.quantity or 0)
        
        return {
            "clearance_amount": clearance_amount,
            "clearance_quantity": clearance_quantity
        }

