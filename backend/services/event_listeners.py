"""
事件监听器 - 数据流转流程自动化

⚠️ v4.6.0 DSS架构重构：已禁用物化视图和C类数据相关事件监听
- 物化视图：Metabase直接查询原始表，不再需要刷新
- C类数据：由Metabase定时计算任务计算（每20分钟）

监听的事件（已禁用）：
- DATA_INGESTED: B类数据入库完成 → 自动刷新物化视图（已禁用）
- MV_REFRESHED: 物化视图刷新完成 → 自动计算C类数据（已禁用）
- A_CLASS_UPDATED: A类数据更新 → 自动重新计算C类数据（已禁用）
"""

from typing import Dict, Any, Optional
from modules.core.logger import get_logger
from backend.utils.events import (
    EventType,
    DataIngestedEvent,
    MVRefreshedEvent,
    AClassUpdatedEvent
)

logger = get_logger(__name__)


class EventListener:
    """事件监听器基类"""
    
    @staticmethod
    def handle_data_ingested(event: DataIngestedEvent) -> None:
        """
        处理B类数据入库完成事件
        
        ⚠️ v4.6.0 DSS架构重构：已禁用物化视图刷新
        根据DSS架构，Metabase直接查询原始表，不再需要刷新物化视图。
        
        Args:
            event: 数据入库事件
        """
        # ⚠️ v4.6.0 DSS架构重构：已禁用物化视图刷新逻辑
        logger.info(
            f"[事件监听] 收到DATA_INGESTED事件（物化视图刷新已禁用）: "
            f"file_id={event.file_id}, domain={event.data_domain}, "
            f"granularity={event.granularity}, rows={event.row_count}"
        )
        logger.debug("[事件监听] DSS架构：Metabase直接查询原始表，无需刷新物化视图")
    
    @staticmethod
    def handle_mv_refreshed(event: MVRefreshedEvent) -> None:
        """
        处理物化视图刷新完成事件
        
        ⚠️ v4.6.0 DSS架构重构：已废弃（Metabase直接查询原始表，无需物化视图）
        此方法保留仅为兼容性，实际不会被调用。
        
        Args:
            event: 物化视图刷新事件
        """
        # ⚠️ v4.6.0 DSS架构重构：已废弃，不再处理物化视图刷新事件
        logger.debug("[事件监听] MV_REFRESHED事件已废弃（DSS架构）")
        logger.info(
            f"[事件监听] 收到MV_REFRESHED事件（C类数据计算已禁用）: "
            f"view={event.view_name}, rows={event.row_count}, "
            f"duration={event.duration_seconds:.2f}s"
        )
        logger.debug("[事件监听] DSS架构：C类数据由Metabase定时计算任务计算")
    
    @staticmethod
    def handle_a_class_updated(event: AClassUpdatedEvent) -> None:
        """
        处理A类数据更新事件
        
        ⚠️ v4.6.0 DSS架构重构：已禁用C类数据重新计算
        根据DSS架构，C类数据应该由Metabase定时计算任务计算（每20分钟）。
        
        Args:
            event: A类数据更新事件
        """
        # ⚠️ v4.6.0 DSS架构重构：已禁用C类数据重新计算逻辑
        logger.info(
            f"[事件监听] 收到A_CLASS_UPDATED事件（C类数据重新计算已禁用）: "
            f"type={event.data_type}, id={event.record_id}, "
            f"action={event.action}"
        )
        logger.debug("[事件监听] DSS架构：C类数据由Metabase定时计算任务计算")
    
    @staticmethod
    def _determine_views_to_refresh(
        data_domain: str,
        granularity: Optional[str]
    ) -> list:
        """
        根据数据域和粒度判断需要刷新的物化视图
        
        Args:
            data_domain: 数据域（orders/products/inventory/traffic/services）
            granularity: 粒度（daily/weekly/monthly/snapshot）
            
        Returns:
            需要刷新的视图名称列表
        """
        views_to_refresh = []
        
        # 根据数据域判断需要刷新的视图
        if data_domain == "orders":
            # 订单数据 → 刷新销售相关视图
            views_to_refresh.extend([
                "mv_daily_sales",
                "mv_order_sales_summary",
                "mv_sales_day_shop_sku",
                "mv_weekly_sales",
                "mv_monthly_sales",
                "mv_financial_overview",
                "mv_pnl_shop_month",
                "mv_profit_analysis"
            ])
        elif data_domain == "products":
            # 产品数据 → 刷新产品相关视图
            views_to_refresh.extend([
                "mv_product_management",
                "mv_product_sales_trend",
                "mv_product_topn_day"
            ])
        elif data_domain == "inventory":
            # 库存数据 → 刷新库存相关视图
            views_to_refresh.extend([
                "mv_inventory_summary",
                "mv_inventory_by_sku",
                "mv_inventory_age_day"
            ])
        elif data_domain in ["traffic", "analytics"]:
            # 流量数据 → 刷新流量相关视图
            views_to_refresh.extend([
                "mv_shop_traffic_day"
            ])
        elif data_domain == "services":
            # 服务数据 → 可能影响多个视图
            views_to_refresh.extend([
                "mv_shop_traffic_day",
                "mv_vendor_performance"
            ])
        
        # 根据粒度进一步筛选（如果粒度是daily，不需要刷新weekly/monthly视图）
        if granularity == "daily":
            views_to_refresh = [
                v for v in views_to_refresh 
                if not v.startswith("mv_weekly") and not v.startswith("mv_monthly")
            ]
        elif granularity == "weekly":
            views_to_refresh = [
                v for v in views_to_refresh 
                if not v.startswith("mv_monthly")
            ]
        
        return list(set(views_to_refresh))  # 去重
    
    @staticmethod
    def _determine_c_class_types_to_calculate(
        view_name: str,
        view_type: Optional[str]
    ) -> list:
        """
        根据物化视图名称判断需要计算的C类数据类型
        
        Args:
            view_name: 物化视图名称
            view_type: 视图类型（sales/inventory/finance/traffic）
            
        Returns:
            需要计算的C类数据类型列表（health_score/achievement_rate/ranking）
        """
        c_class_types = []
        
        # 根据视图名称判断
        if "shop" in view_name.lower() and "sales" in view_name.lower():
            # 店铺销售视图 → 计算健康度评分和排名
            c_class_types.extend(["health_score", "ranking"])
        elif "daily_sales" in view_name or "order_sales" in view_name:
            # 销售汇总视图 → 计算达成率
            c_class_types.append("achievement_rate")
        elif "traffic" in view_name.lower():
            # 流量视图 → 计算健康度评分
            c_class_types.append("health_score")
        
        # 根据视图类型判断
        if view_type == "sales":
            if "achievement_rate" not in c_class_types:
                c_class_types.append("achievement_rate")
        
        return list(set(c_class_types))  # 去重
    
    @staticmethod
    def _determine_c_class_types_to_recalculate(
        data_type: str,
        action: str
    ) -> list:
        """
        根据A类数据类型和操作判断需要重新计算的C类数据类型
        
        Args:
            data_type: A类数据类型（sales_campaign/target/performance_config）
            action: 操作类型（create/update/delete）
            
        Returns:
            需要重新计算的C类数据类型列表
        """
        c_class_types = []
        
        if data_type == "sales_campaign":
            # 销售战役更新 → 重新计算达成率
            c_class_types.append("achievement_rate")
        elif data_type == "target":
            # 目标更新 → 重新计算达成率
            c_class_types.append("achievement_rate")
        elif data_type == "performance_config":
            # 绩效配置更新 → 重新计算健康度评分
            c_class_types.append("health_score")
        
        return c_class_types


# 全局事件监听器实例
event_listener = EventListener()

