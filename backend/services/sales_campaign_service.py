#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售战役服务

负责销售战役的达成率计算逻辑（C类数据）
从路由层提取业务逻辑，符合分层架构规范
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import date, datetime
from typing import Dict, Any, Optional

from modules.core.db import (
    SalesCampaign,
    SalesCampaignShop,
    FactOrder
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SalesCampaignService:
    """销售战役服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_campaign_achievement(self, campaign_id: int) -> Dict[str, Any]:
        """
        计算战役达成情况（C类数据：系统自动计算）
        
        从fact_orders表聚合计算实际销售额和订单数
        更新战役和参与店铺的达成数据
        
        Args:
            campaign_id: 战役ID
            
        Returns:
            计算结果的字典，包含战役信息和店铺信息
        """
        # 查询战役
        campaign = self.db.execute(
            select(SalesCampaign).where(SalesCampaign.id == campaign_id)
        ).scalar_one_or_none()
        
        if not campaign:
            raise ValueError(f"战役不存在: {campaign_id}")
        
        # 查询参与店铺
        shops = self.db.execute(
            select(SalesCampaignShop).where(
                SalesCampaignShop.campaign_id == campaign_id
            )
        ).scalars().all()
        
        total_actual_amount = 0.0
        total_actual_quantity = 0
        
        # 计算每个店铺的达成情况
        for shop in shops:
            if not shop.platform_code or not shop.shop_id:
                continue
            
            # 从fact_orders聚合计算
            result = self.db.execute(
                select(
                    func.coalesce(func.sum(FactOrder.total_amount_rmb), 0).label("amount"),
                    func.count(FactOrder.order_id).label("quantity")
                ).where(
                    FactOrder.platform_code == shop.platform_code,
                    FactOrder.shop_id == shop.shop_id,
                    FactOrder.order_date_local >= campaign.start_date,
                    FactOrder.order_date_local <= campaign.end_date,
                    FactOrder.order_status.in_(["completed", "paid"])  # 只统计已完成/已付款订单
                )
            ).first()
            
            shop.actual_amount = float(result.amount or 0)
            shop.actual_quantity = int(result.quantity or 0)
            shop.achievement_rate = (
                (shop.actual_amount / shop.target_amount * 100) if shop.target_amount > 0 else 0.0
            )
            
            total_actual_amount += shop.actual_amount
            total_actual_quantity += shop.actual_quantity
        
        # 更新店铺排名
        shops_sorted = sorted(shops, key=lambda x: x.actual_amount, reverse=True)
        for rank, shop in enumerate(shops_sorted, start=1):
            shop.rank = rank
        
        # 更新战役总体达成情况
        campaign.actual_amount = total_actual_amount
        campaign.actual_quantity = total_actual_quantity
        campaign.achievement_rate = (
            (total_actual_amount / campaign.target_amount * 100) if campaign.target_amount > 0 else 0.0
        )
        
        # 自动更新状态
        if campaign.status == "pending" and campaign.start_date <= date.today() <= campaign.end_date:
            campaign.status = "active"
        elif campaign.end_date < date.today():
            campaign.status = "completed"
        
        campaign.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(campaign)
        
        return {
            "campaign": campaign,
            "shops": shops,
            "total_actual_amount": total_actual_amount,
            "total_actual_quantity": total_actual_quantity,
            "achievement_rate": campaign.achievement_rate
        }
    
    def calculate_all_campaigns(self) -> Dict[str, Any]:
        """
        批量计算所有战役的达成情况
        
        Returns:
            计算结果统计
        """
        campaigns = self.db.execute(
            select(SalesCampaign).where(
                SalesCampaign.status.in_(["pending", "active"])
            )
        ).scalars().all()
        
        results = []
        success_count = 0
        failed_count = 0
        
        for campaign in campaigns:
            try:
                result = self.calculate_campaign_achievement(campaign.id)
                results.append({
                    "campaign_id": campaign.id,
                    "campaign_name": campaign.campaign_name,
                    "achievement_rate": result["achievement_rate"],
                    "status": "success"
                })
                success_count += 1
            except Exception as e:
                logger.error(f"计算战役{campaign.id}达成情况失败: {e}", exc_info=True)
                results.append({
                    "campaign_id": campaign.id,
                    "campaign_name": campaign.campaign_name,
                    "status": "failed",
                    "error": str(e)
                })
                failed_count += 1
        
        return {
            "total": len(campaigns),
            "success": success_count,
            "failed": failed_count,
            "results": results
        }

