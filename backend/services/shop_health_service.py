#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
店铺健康度评分服务（v4.11.0新增）

功能：
1. 计算店铺健康度评分（0-100分）
2. 计算各项得分（GMV、转化、库存、服务）
3. 评估风险等级
4. 生成店铺预警

评分规则：
- GMV得分（0-30分）：基于GMV排名和增长率
- 转化得分（0-25分）：基于转化率排名
- 库存得分（0-25分）：基于库存周转率
- 服务得分（0-20分）：基于客户满意度

总分 = GMV得分 + 转化得分 + 库存得分 + 服务得分
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import math

from modules.core.db import (
    ShopHealthScore,
    ShopAlert,
    FactOrder,
    FactProductMetric,
    DimShop
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ShopHealthService:
    """店铺健康度评分服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_health_score(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date,
        granularity: str = "daily"
    ) -> Dict[str, Any]:
        """
        计算店铺健康度评分
        
        参数：
            platform_code: 平台代码
            shop_id: 店铺ID
            metric_date: 指标日期
            granularity: 粒度（daily/weekly/monthly）
        
        返回：
            {
                "health_score": 85.5,
                "gmv_score": 28.0,
                "conversion_score": 22.0,
                "inventory_score": 20.0,
                "service_score": 15.5,
                "risk_level": "low",
                "risk_factors": []
            }
        """
        try:
            # 计算时间范围
            if granularity == "daily":
                start_date = metric_date
                end_date = metric_date
            elif granularity == "weekly":
                # 计算周的开始和结束日期
                days_since_monday = metric_date.weekday()
                start_date = metric_date - timedelta(days=days_since_monday)
                end_date = start_date + timedelta(days=6)
            elif granularity == "monthly":
                # 计算月的开始和结束日期
                start_date = metric_date.replace(day=1)
                if start_date.month == 12:
                    end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
            else:
                start_date = metric_date
                end_date = metric_date
            
            # 1. 获取店铺基础指标
            shop_metrics = self._get_shop_metrics(platform_code, shop_id, start_date, end_date)
            
            # 2. 获取所有店铺的指标（用于排名）
            all_shops_metrics = self._get_all_shops_metrics(start_date, end_date)
            
            # 3. 计算各项得分
            gmv_score = self._calculate_gmv_score(shop_metrics, all_shops_metrics)
            conversion_score = self._calculate_conversion_score(shop_metrics, all_shops_metrics)
            inventory_score = self._calculate_inventory_score(shop_metrics, all_shops_metrics)
            service_score = self._calculate_service_score(shop_metrics, all_shops_metrics)
            
            # 4. 计算总分
            health_score = gmv_score + conversion_score + inventory_score + service_score
            
            # 5. 评估风险等级
            risk_level, risk_factors = self._assess_risk(
                health_score,
                shop_metrics,
                all_shops_metrics
            )
            
            # 6. 保存或更新健康度评分
            existing_score = self.db.execute(
                select(ShopHealthScore).where(
                    ShopHealthScore.platform_code == platform_code,
                    ShopHealthScore.shop_id == shop_id,
                    ShopHealthScore.metric_date == metric_date,
                    ShopHealthScore.granularity == granularity
                )
            ).scalar_one_or_none()
            
            if existing_score:
                existing_score.health_score = health_score
                existing_score.gmv_score = gmv_score
                existing_score.conversion_score = conversion_score
                existing_score.inventory_score = inventory_score
                existing_score.service_score = service_score
                existing_score.gmv = shop_metrics.get("gmv", 0.0)
                existing_score.conversion_rate = shop_metrics.get("conversion_rate", 0.0)
                existing_score.inventory_turnover = shop_metrics.get("inventory_turnover", 0.0)
                existing_score.customer_satisfaction = shop_metrics.get("customer_satisfaction", 0.0)
                existing_score.risk_level = risk_level
                existing_score.risk_factors = risk_factors
                existing_score.updated_at = datetime.utcnow()
                score = existing_score
            else:
                score = ShopHealthScore(
                    platform_code=platform_code,
                    shop_id=shop_id,
                    metric_date=metric_date,
                    granularity=granularity,
                    health_score=health_score,
                    gmv_score=gmv_score,
                    conversion_score=conversion_score,
                    inventory_score=inventory_score,
                    service_score=service_score,
                    gmv=shop_metrics.get("gmv", 0.0),
                    conversion_rate=shop_metrics.get("conversion_rate", 0.0),
                    inventory_turnover=shop_metrics.get("inventory_turnover", 0.0),
                    customer_satisfaction=shop_metrics.get("customer_satisfaction", 0.0),
                    risk_level=risk_level,
                    risk_factors=risk_factors
                )
                self.db.add(score)
            
            self.db.commit()
            self.db.refresh(score)
            
            return {
                "health_score": health_score,
                "gmv_score": gmv_score,
                "conversion_score": conversion_score,
                "inventory_score": inventory_score,
                "service_score": service_score,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "metrics": shop_metrics
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"计算店铺健康度评分失败: {e}", exc_info=True)
            raise
    
    def _get_shop_metrics(
        self,
        platform_code: str,
        shop_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """获取店铺基础指标"""
        # 从fact_orders计算GMV和订单数
        order_result = self.db.execute(
            select(
                func.coalesce(func.sum(FactOrder.total_amount_rmb), 0).label("gmv"),
                func.count(FactOrder.order_id).label("order_count")
            ).where(
                FactOrder.platform_code == platform_code,
                FactOrder.shop_id == shop_id,
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            )
        ).first()
        
        gmv = float(order_result.gmv or 0)
        order_count = int(order_result.order_count or 0)
        
        # 从fact_product_metrics计算转化率和访客数
        metric_result = self.db.execute(
            select(
                func.coalesce(func.sum(FactProductMetric.unique_visitors), 0).label("uv"),
                func.coalesce(func.sum(FactProductMetric.page_views), 0).label("pv")
            ).where(
                FactProductMetric.platform_code == platform_code,
                FactProductMetric.shop_id == shop_id,
                FactProductMetric.metric_date >= start_date,
                FactProductMetric.metric_date <= end_date,
                FactProductMetric.data_domain == "products"
            )
        ).first()
        
        uv = float(metric_result.uv or 0)
        pv = float(metric_result.pv or 0)
        
        # 计算转化率
        conversion_rate = (order_count / uv * 100) if uv > 0 else 0.0
        
        # 计算库存周转率（年化）
        # 库存周转率 = 365 / 库存周转天数
        # 库存周转天数 = 可用库存 / (近30天日均销量)
        # 近30天日均销量 = sales_volume_30d / 30
        inventory_result = self.db.execute(
            select(
                func.coalesce(func.sum(FactProductMetric.available_stock), func.sum(FactProductMetric.stock), 0).label("total_available_stock"),
                func.coalesce(func.sum(FactProductMetric.sales_volume_30d), func.sum(FactProductMetric.sales_volume), 0).label("sales_volume_30d")
            ).where(
                FactProductMetric.platform_code == platform_code,
                FactProductMetric.shop_id == shop_id,
                FactProductMetric.metric_date >= start_date,
                FactProductMetric.metric_date <= end_date,
                FactProductMetric.data_domain.in_(["products", "inventory"])  # 支持products和inventory域
            )
        ).first()
        
        total_available_stock = float(inventory_result.total_available_stock or 0)
        sales_volume_30d = float(inventory_result.sales_volume_30d or 0)
        
        if sales_volume_30d > 0 and total_available_stock > 0:
            # 库存周转天数 = 可用库存 / (近30天日均销量)
            daily_avg_sales = sales_volume_30d / 30.0
            inventory_turnover_days = total_available_stock / daily_avg_sales if daily_avg_sales > 0 else 999.0
            # 库存周转率（年化）= 365 / 库存周转天数
            inventory_turnover = 365.0 / inventory_turnover_days if inventory_turnover_days > 0 else 0.0
        else:
            inventory_turnover = 0.0
        
        # 计算客户满意度（从fact_product_metrics的rating字段计算平均值）
        rating_result = self.db.execute(
            select(
                func.coalesce(func.avg(FactProductMetric.rating), 0).label("avg_rating"),
                func.count(FactProductMetric.rating).label("rating_count")
            ).where(
                FactProductMetric.platform_code == platform_code,
                FactProductMetric.shop_id == shop_id,
                FactProductMetric.metric_date >= start_date,
                FactProductMetric.metric_date <= end_date,
                FactProductMetric.data_domain == "products",
                FactProductMetric.rating.isnot(None),
                FactProductMetric.rating > 0
            )
        ).first()
        
        customer_satisfaction = float(rating_result.avg_rating or 0) if rating_result.rating_count and rating_result.rating_count > 0 else 0.0
        
        return {
            "gmv": gmv,
            "order_count": order_count,
            "uv": uv,
            "pv": pv,
            "conversion_rate": conversion_rate,
            "inventory_turnover": inventory_turnover,
            "customer_satisfaction": customer_satisfaction
        }
    
    def _get_all_shops_metrics(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """获取所有店铺的指标（用于排名）"""
        # 从fact_orders聚合所有店铺的GMV
        shops_gmv = self.db.execute(
            select(
                FactOrder.platform_code,
                FactOrder.shop_id,
                func.coalesce(func.sum(FactOrder.total_amount_rmb), 0).label("gmv"),
                func.count(FactOrder.order_id).label("order_count")
            ).where(
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            ).group_by(FactOrder.platform_code, FactOrder.shop_id)
        ).all()
        
        # 从fact_product_metrics聚合所有店铺的UV
        shops_uv = self.db.execute(
            select(
                FactProductMetric.platform_code,
                FactProductMetric.shop_id,
                func.coalesce(func.sum(FactProductMetric.unique_visitors), 0).label("uv")
            ).where(
                FactProductMetric.metric_date >= start_date,
                FactProductMetric.metric_date <= end_date,
                FactProductMetric.data_domain == "products"
            ).group_by(FactProductMetric.platform_code, FactProductMetric.shop_id)
        ).all()
        
        # 合并数据
        shops_dict = {}
        for row in shops_gmv:
            key = f"{row.platform_code}_{row.shop_id}"
            shops_dict[key] = {
                "platform_code": row.platform_code,
                "shop_id": row.shop_id,
                "gmv": float(row.gmv or 0),
                "order_count": int(row.order_count or 0),
                "uv": 0.0
            }
        
        for row in shops_uv:
            key = f"{row.platform_code}_{row.shop_id}"
            if key in shops_dict:
                shops_dict[key]["uv"] = float(row.uv or 0)
        
        # 计算转化率
        shops_list = []
        for shop_data in shops_dict.values():
            shop_data["conversion_rate"] = (
                (shop_data["order_count"] / shop_data["uv"] * 100) if shop_data["uv"] > 0 else 0.0
            )
            shops_list.append(shop_data)
        
        return shops_list
    
    def _calculate_gmv_score(
        self,
        shop_metrics: Dict[str, Any],
        all_shops_metrics: List[Dict[str, Any]]
    ) -> float:
        """计算GMV得分（0-30分）"""
        if not all_shops_metrics:
            return 0.0
        
        # 按GMV排序
        sorted_shops = sorted(all_shops_metrics, key=lambda x: x["gmv"], reverse=True)
        total_shops = len(sorted_shops)
        
        # 找到当前店铺的排名
        shop_gmv = shop_metrics.get("gmv", 0.0)
        rank = 1
        for i, shop in enumerate(sorted_shops):
            if shop["gmv"] <= shop_gmv:
                rank = i + 1
                break
        
        # 计算得分：排名越靠前得分越高
        # 前10%：30分，前30%：25分，前50%：20分，前70%：15分，其他：10分
        percentile = (rank / total_shops) * 100
        
        if percentile <= 10:
            return 30.0
        elif percentile <= 30:
            return 25.0
        elif percentile <= 50:
            return 20.0
        elif percentile <= 70:
            return 15.0
        else:
            return 10.0
    
    def _calculate_conversion_score(
        self,
        shop_metrics: Dict[str, Any],
        all_shops_metrics: List[Dict[str, Any]]
    ) -> float:
        """计算转化得分（0-25分）"""
        if not all_shops_metrics:
            return 0.0
        
        # 按转化率排序
        sorted_shops = sorted(all_shops_metrics, key=lambda x: x["conversion_rate"], reverse=True)
        total_shops = len(sorted_shops)
        
        # 找到当前店铺的排名
        shop_conversion = shop_metrics.get("conversion_rate", 0.0)
        rank = 1
        for i, shop in enumerate(sorted_shops):
            if shop["conversion_rate"] <= shop_conversion:
                rank = i + 1
                break
        
        # 计算得分：排名越靠前得分越高
        percentile = (rank / total_shops) * 100
        
        if percentile <= 10:
            return 25.0
        elif percentile <= 30:
            return 20.0
        elif percentile <= 50:
            return 15.0
        elif percentile <= 70:
            return 10.0
        else:
            return 5.0
    
    def _calculate_inventory_score(
        self,
        shop_metrics: Dict[str, Any],
        all_shops_metrics: List[Dict[str, Any]]
    ) -> float:
        """计算库存得分（0-25分）"""
        # TODO: 需要根据实际库存周转率数据计算
        # 临时实现：基于库存周转率阈值
        inventory_turnover = shop_metrics.get("inventory_turnover", 0.0)
        
        if inventory_turnover >= 15:
            return 25.0
        elif inventory_turnover >= 12:
            return 20.0
        elif inventory_turnover >= 10:
            return 15.0
        elif inventory_turnover >= 8:
            return 10.0
        else:
            return 5.0
    
    def _calculate_service_score(
        self,
        shop_metrics: Dict[str, Any],
        all_shops_metrics: List[Dict[str, Any]]
    ) -> float:
        """计算服务得分（0-20分）"""
        # 基于客户满意度（0-5分）
        customer_satisfaction = shop_metrics.get("customer_satisfaction", 0.0)
        
        # 转换为0-20分
        if customer_satisfaction >= 4.5:
            return 20.0
        elif customer_satisfaction >= 4.0:
            return 16.0
        elif customer_satisfaction >= 3.5:
            return 12.0
        elif customer_satisfaction >= 3.0:
            return 8.0
        else:
            return 4.0
    
    def _assess_risk(
        self,
        health_score: float,
        shop_metrics: Dict[str, Any],
        all_shops_metrics: List[Dict[str, Any]]
    ) -> tuple[str, List[str]]:
        """评估风险等级"""
        risk_factors = []
        
        # 健康度总分风险
        if health_score < 60:
            risk_factors.append("健康度总分过低")
        elif health_score < 70:
            risk_factors.append("健康度总分偏低")
        
        # 转化率风险
        conversion_rate = shop_metrics.get("conversion_rate", 0.0)
        if conversion_rate < 2.0:
            risk_factors.append("转化率过低")
        elif conversion_rate < 3.0:
            risk_factors.append("转化率偏低")
        
        # 库存周转风险
        inventory_turnover = shop_metrics.get("inventory_turnover", 0.0)
        if inventory_turnover < 8:
            risk_factors.append("库存周转率过低")
        
        # 客户满意度风险
        customer_satisfaction = shop_metrics.get("customer_satisfaction", 0.0)
        if customer_satisfaction < 3.0:
            risk_factors.append("客户满意度过低")
        
        # 确定风险等级
        if health_score < 60 or len(risk_factors) >= 3:
            risk_level = "high"
        elif health_score < 70 or len(risk_factors) >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return risk_level, risk_factors
    
    def generate_alerts(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date
    ) -> List[Dict[str, Any]]:
        """
        生成店铺预警
        
        基于健康度评分和业务规则生成预警
        """
        try:
            # 获取最新的健康度评分
            health_score = self.db.execute(
                select(ShopHealthScore).where(
                    ShopHealthScore.platform_code == platform_code,
                    ShopHealthScore.shop_id == shop_id,
                    ShopHealthScore.metric_date == metric_date
                ).order_by(ShopHealthScore.created_at.desc())
            ).scalar_one_or_none()
            
            if not health_score:
                return []
            
            alerts = []
            
            # 健康度预警
            if health_score.health_score < 60:
                alerts.append({
                    "alert_type": "health_score_critical",
                    "alert_level": "critical",
                    "title": "店铺健康度严重不足",
                    "message": f"店铺健康度评分仅为{health_score.health_score:.1f}分，需要立即关注",
                    "metric_value": health_score.health_score,
                    "threshold": 60.0,
                    "metric_unit": "分"
                })
            elif health_score.health_score < 70:
                alerts.append({
                    "alert_type": "health_score_warning",
                    "alert_level": "warning",
                    "title": "店铺健康度偏低",
                    "message": f"店铺健康度评分为{health_score.health_score:.1f}分，建议关注",
                    "metric_value": health_score.health_score,
                    "threshold": 70.0,
                    "metric_unit": "分"
                })
            
            # 转化率预警
            if health_score.conversion_rate < 2.0:
                alerts.append({
                    "alert_type": "conversion_rate_critical",
                    "alert_level": "critical",
                    "title": "转化率严重不足",
                    "message": f"店铺转化率仅为{health_score.conversion_rate:.2f}%，远低于行业平均水平",
                    "metric_value": health_score.conversion_rate,
                    "threshold": 2.0,
                    "metric_unit": "%"
                })
            elif health_score.conversion_rate < 3.0:
                alerts.append({
                    "alert_type": "conversion_rate_warning",
                    "alert_level": "warning",
                    "title": "转化率偏低",
                    "message": f"店铺转化率为{health_score.conversion_rate:.2f}%，建议优化",
                    "metric_value": health_score.conversion_rate,
                    "threshold": 3.0,
                    "metric_unit": "%"
                })
            
            # 库存周转预警
            if health_score.inventory_turnover < 8:
                alerts.append({
                    "alert_type": "inventory_turnover_warning",
                    "alert_level": "warning",
                    "title": "库存周转率偏低",
                    "message": f"店铺库存周转率为{health_score.inventory_turnover:.1f}次，可能存在滞销风险",
                    "metric_value": health_score.inventory_turnover,
                    "threshold": 8.0,
                    "metric_unit": "次"
                })
            
            # 保存预警到数据库
            for alert_data in alerts:
                # 检查是否已存在相同预警
                existing_alert = self.db.execute(
                    select(ShopAlert).where(
                        ShopAlert.platform_code == platform_code,
                        ShopAlert.shop_id == shop_id,
                        ShopAlert.alert_type == alert_data["alert_type"],
                        ShopAlert.is_resolved == False
                    )
                ).scalar_one_or_none()
                
                if not existing_alert:
                    alert = ShopAlert(
                        platform_code=platform_code,
                        shop_id=shop_id,
                        alert_type=alert_data["alert_type"],
                        alert_level=alert_data["alert_level"],
                        title=alert_data["title"],
                        message=alert_data["message"],
                        metric_value=alert_data["metric_value"],
                        threshold=alert_data["threshold"],
                        metric_unit=alert_data["metric_unit"]
                    )
                    self.db.add(alert)
            
            self.db.commit()
            
            return alerts
        except Exception as e:
            self.db.rollback()
            logger.error(f"生成店铺预警失败: {e}", exc_info=True)
            raise

