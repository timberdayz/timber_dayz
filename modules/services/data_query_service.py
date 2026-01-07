#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据查询服务

为前端提供统一的数据查询接口，支持：
- 订单数据查询
- 产品指标查询
- Catalog状态查询
- 数据聚合（日/周/月）
- 查询缓存（5分钟TTL）

使用示例:
    from modules.services.data_query_service import DataQueryService
    
    service = DataQueryService()
    
    # 查询订单
    orders = service.get_orders(
        platforms=['shopee', 'tiktok'],
        start_date='2024-10-01',
        end_date='2024-10-16'
    )
    
    # 查询产品指标
    metrics = service.get_product_metrics(
        platforms=['shopee'],
        metric_type='gmv',
        start_date='2024-10-01',
        end_date='2024-10-16'
    )
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from modules.core.secrets_manager import get_secrets_manager
from modules.services.cache_service import cached
from modules.core.logger import get_logger

logger = get_logger(__name__)


class DataQueryService:
    """
    统一数据查询服务
    
    提供各种数据查询接口，自动处理：
    - 数据库连接管理
    - 查询结果缓存
    - 数据清洗和格式化
    - 错误处理
    """
    
    def __init__(self):
        """初始化数据查询服务"""
        self._engine: Optional[Engine] = None
    
    def _get_engine(self) -> Engine:
        """获取数据库引擎（懒加载）"""
        if self._engine is None:
            url = os.getenv('DATABASE_URL')
            if not url:
                sm = get_secrets_manager()
                db_path = sm.get_unified_database_path()
                # 确保使用绝对路径
                if not db_path.is_absolute():
                    db_path = db_path.resolve()
                url = f"sqlite:///{db_path}"
            self._engine = create_engine(url, pool_pre_ping=True, future=True)
        return self._engine
    
    # ========================================
    # 订单数据查询
    # ========================================
    
    @cached(ttl_seconds=300)  # 5分钟缓存
    def get_orders(
        self,
        platforms: Optional[List[str]] = None,
        shops: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        查询订单数据
        
        Args:
            platforms: 平台列表，如['shopee', 'tiktok']
            shops: 店铺ID列表
            start_date: 开始日期，格式YYYY-MM-DD
            end_date: 结束日期，格式YYYY-MM-DD
            status: 订单状态过滤
            limit: 返回记录数限制
        
        Returns:
            订单数据DataFrame，包含列：
                order_id, platform_code, shop_id, order_date_local,
                total_amount, currency, order_status, payment_status
        """
        # 构建查询
        sql = """
            SELECT 
                order_id,
                platform_code,
                shop_id,
                order_date_local,
                total_amount,
                total_amount_rmb,
                currency,
                order_status,
                payment_status,
                is_cancelled,
                is_refunded
            FROM fact_orders
            WHERE 1=1
        """
        
        params = {}
        
        if platforms:
            placeholders = ','.join([f':platform_{i}' for i in range(len(platforms))])
            sql += f" AND platform_code IN ({placeholders})"
            for i, p in enumerate(platforms):
                params[f'platform_{i}'] = p
        
        if shops:
            placeholders = ','.join([f':shop_{i}' for i in range(len(shops))])
            sql += f" AND shop_id IN ({placeholders})"
            for i, s in enumerate(shops):
                params[f'shop_{i}'] = s
        
        if start_date:
            sql += " AND order_date_local >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            sql += " AND order_date_local <= :end_date"
            params['end_date'] = end_date
        
        if status:
            sql += " AND order_status = :status"
            params['status'] = status
        
        sql += " ORDER BY order_date_local DESC"
        sql += f" LIMIT {limit}"
        
        # 执行查询
        try:
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params)
            return df
        except Exception as e:
            # 返回空DataFrame（带正确的列）
            return pd.DataFrame(columns=[
                'order_id', 'platform_code', 'shop_id', 'order_date_local',
                'total_amount', 'total_amount_rmb', 'currency', 
                'order_status', 'payment_status', 'is_cancelled', 'is_refunded'
            ])
    
    @cached(ttl_seconds=300)
    def get_order_summary(
        self,
        platforms: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = 'day'  # day/week/month/platform/shop
    ) -> pd.DataFrame:
        """
        订单汇总统计
        
        Args:
            platforms: 平台列表
            start_date: 开始日期
            end_date: 结束日期
            group_by: 分组方式（day/week/month/platform/shop）
        
        Returns:
            汇总数据，包含：订单数、总金额、平均订单金额等
        """
        # 构建分组字段
        group_fields = []
        select_fields = []
        
        if group_by == 'day':
            select_fields.append("order_date_local as date")
            group_fields.append("order_date_local")
        elif group_by == 'week':
            select_fields.append("strftime('%Y-W%W', order_date_local) as week")
            group_fields.append("strftime('%Y-W%W', order_date_local)")
        elif group_by == 'month':
            select_fields.append("strftime('%Y-%m', order_date_local) as month")
            group_fields.append("strftime('%Y-%m', order_date_local)")
        elif group_by == 'platform':
            select_fields.append("platform_code")
            group_fields.append("platform_code")
        elif group_by == 'shop':
            select_fields.append("platform_code, shop_id")
            group_fields.extend(["platform_code", "shop_id"])
        
        # 构建SQL
        sql = f"""
            SELECT 
                {', '.join(select_fields)},
                COUNT(*) as order_count,
                SUM(total_amount) as total_amount,
                SUM(total_amount_rmb) as total_amount_rmb,
                AVG(total_amount) as avg_amount,
                SUM(CASE WHEN is_cancelled = 1 THEN 1 ELSE 0 END) as cancelled_count,
                SUM(CASE WHEN is_refunded = 1 THEN 1 ELSE 0 END) as refunded_count
            FROM fact_orders
            WHERE 1=1
        """
        
        params = {}
        
        if platforms:
            placeholders = ','.join([f':platform_{i}' for i in range(len(platforms))])
            sql += f" AND platform_code IN ({placeholders})"
            for i, p in enumerate(platforms):
                params[f'platform_{i}'] = p
        
        if start_date:
            sql += " AND order_date_local >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            sql += " AND order_date_local <= :end_date"
            params['end_date'] = end_date
        
        sql += f" GROUP BY {', '.join(group_fields)}"
        sql += f" ORDER BY {group_fields[0]} DESC"
        
        try:
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params)
            return df
        except Exception:
            return pd.DataFrame()
    
    # ========================================
    # 产品指标查询
    # ========================================
    
    @cached(ttl_seconds=300)
    def get_product_metrics(
        self,
        platforms: Optional[List[str]] = None,
        shops: Optional[List[str]] = None,
        skus: Optional[List[str]] = None,
        metric_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        查询产品指标
        
        Args:
            platforms: 平台列表
            shops: 店铺ID列表
            skus: SKU列表
            metric_type: 指标类型（gmv/units_sold/page_views等）
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回记录数限制
        
        Returns:
            产品指标DataFrame
        """
        sql = """
            SELECT 
                m.platform_code,
                m.shop_id,
                m.platform_sku,
                p.product_title,
                m.metric_date,
                m.metric_type,
                m.metric_value,
                m.currency,
                m.metric_value_rmb,
                m.granularity
            FROM fact_product_metrics m
            LEFT JOIN dim_products p 
                ON m.platform_code = p.platform_code 
                AND m.shop_id = p.shop_id 
                AND m.platform_sku = p.platform_sku
            WHERE 1=1
        """
        
        params = {}
        
        if platforms:
            placeholders = ','.join([f':platform_{i}' for i in range(len(platforms))])
            sql += f" AND m.platform_code IN ({placeholders})"
            for i, p in enumerate(platforms):
                params[f'platform_{i}'] = p
        
        if shops:
            placeholders = ','.join([f':shop_{i}' for i in range(len(shops))])
            sql += f" AND m.shop_id IN ({placeholders})"
            for i, s in enumerate(shops):
                params[f'shop_{i}'] = s
        
        if skus:
            placeholders = ','.join([f':sku_{i}' for i in range(len(skus))])
            sql += f" AND m.platform_sku IN ({placeholders})"
            for i, sku in enumerate(skus):
                params[f'sku_{i}'] = sku
        
        if metric_type:
            sql += " AND m.metric_type = :metric_type"
            params['metric_type'] = metric_type
        
        if start_date:
            sql += " AND m.metric_date >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            sql += " AND m.metric_date <= :end_date"
            params['end_date'] = end_date
        
        sql += " ORDER BY m.metric_date DESC"
        sql += f" LIMIT {limit}"
        
        try:
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params)
            return df
        except Exception:
            return pd.DataFrame()
    
    @cached(ttl_seconds=300)
    def get_top_products(
        self,
        platforms: Optional[List[str]] = None,
        metric_type: str = 'gmv',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        获取Top产品排行榜
        
        Args:
            platforms: 平台列表
            metric_type: 排序指标（gmv/units_sold）
            start_date: 开始日期
            end_date: 结束日期
            top_n: 返回Top N
        
        Returns:
            Top产品DataFrame
        """
        sql = """
            SELECT 
                m.platform_code,
                m.shop_id,
                m.platform_sku,
                p.product_title,
                SUM(m.metric_value) as total_value,
                SUM(m.metric_value_rmb) as total_value_rmb
            FROM fact_product_metrics m
            LEFT JOIN dim_products p 
                ON m.platform_code = p.platform_code 
                AND m.shop_id = p.shop_id 
                AND m.platform_sku = p.platform_sku
            WHERE m.metric_type = :metric_type
        """
        
        params = {'metric_type': metric_type}
        
        if platforms:
            placeholders = ','.join([f':platform_{i}' for i in range(len(platforms))])
            sql += f" AND m.platform_code IN ({placeholders})"
            for i, p in enumerate(platforms):
                params[f'platform_{i}'] = p
        
        if start_date:
            sql += " AND m.metric_date >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            sql += " AND m.metric_date <= :end_date"
            params['end_date'] = end_date
        
        sql += """
            GROUP BY m.platform_code, m.shop_id, m.platform_sku, p.product_title
            ORDER BY total_value_rmb DESC
        """
        sql += f" LIMIT {top_n}"
        
        try:
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params)
            return df
        except Exception:
            return pd.DataFrame()
    
    # ========================================
    # Catalog状态查询
    # ========================================
    
    @cached(ttl_seconds=60)  # 1分钟缓存（状态变化快）
    def get_catalog_status(self) -> Dict[str, Any]:
        """
        获取Catalog状态统计
        
        Returns:
            状态统计字典，包含：
                - total: 总文件数
                - by_status: 按状态分组统计
                - by_domain: 按数据域分组统计
                - by_platform: 按平台分组统计
        """
        try:
            with self._get_engine().connect() as conn:
                # 总数
                total = conn.execute(text(
                    "SELECT COUNT(*) FROM catalog_files"
                )).scalar()
                
                # 按状态统计
                status_df = pd.read_sql_query(text("""
                    SELECT status, COUNT(*) as count
                    FROM catalog_files
                    GROUP BY status
                """), conn)
                
                # 按数据域统计
                domain_df = pd.read_sql_query(text("""
                    SELECT COALESCE(data_domain, 'unknown') as domain, COUNT(*) as count
                    FROM catalog_files
                    GROUP BY data_domain
                """), conn)
                
                # 按平台统计
                platform_df = pd.read_sql_query(text("""
                    SELECT COALESCE(platform_code, 'unknown') as platform, COUNT(*) as count
                    FROM catalog_files
                    GROUP BY platform_code
                """), conn)
                
                return {
                    'total': total,
                    'by_status': status_df.to_dict('records'),
                    'by_domain': domain_df.to_dict('records'),
                    'by_platform': platform_df.to_dict('records'),
                }
        except Exception:
            return {
                'total': 0,
                'by_status': [],
                'by_domain': [],
                'by_platform': [],
            }
    
    @cached(ttl_seconds=60)
    def get_recent_files(
        self,
        status: Optional[str] = None,
        limit: int = 20
    ) -> pd.DataFrame:
        """
        获取最近处理的文件
        
        Args:
            status: 状态过滤（pending/ingested/failed）
            limit: 返回记录数
        
        Returns:
            文件列表DataFrame
        """
        sql = """
            SELECT 
                id,
                file_name,
                platform_code,
                shop_id,
                data_domain,
                status,
                error_message,
                first_seen_at,
                last_processed_at
            FROM catalog_files
            WHERE 1=1
        """
        
        params = {}
        
        if status:
            sql += " AND status = :status"
            params['status'] = status
        
        sql += " ORDER BY first_seen_at DESC"
        sql += f" LIMIT {limit}"
        
        try:
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params)
            return df
        except Exception:
            return pd.DataFrame()
    
    # ========================================
    # 数据聚合服务
    # ========================================
    
    @cached(ttl_seconds=600)  # 10分钟缓存
    def get_dashboard_summary(
        self,
        platforms: Optional[List[str]] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取仪表盘汇总数据
        
        Args:
            platforms: 平台列表
            days: 统计天数
        
        Returns:
            汇总数据字典，包含：
                - order_count: 订单总数
                - total_gmv: 总GMV（RMB）
                - avg_order_amount: 平均订单金额
                - top_products: Top 5产品
                - daily_trend: 每日趋势
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # 订单统计
        order_summary = self.get_order_summary(
            platforms=platforms,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            group_by='day'
        )
        
        # Top产品
        top_products = self.get_top_products(
            platforms=platforms,
            metric_type='gmv',
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            top_n=5
        )
        
        # Catalog状态
        catalog_status = self.get_catalog_status()
        
        return {
            'period': f'近{days}天',
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'order_summary': order_summary.to_dict('records') if not order_summary.empty else [],
            'top_products': top_products.to_dict('records') if not top_products.empty else [],
            'catalog_status': catalog_status,
        }
    
    # ========================================
    # 产品指标统一查询（层级感知）
    # ========================================
    
    @cached(ttl_seconds=300)
    def get_product_metrics_unified(
        self,
        platforms: Optional[List[str]] = None,
        shops: Optional[List[str]] = None,
        skus: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_scope: str = 'auto',  # auto | product | variant | both
        include_metadata: bool = True
    ) -> pd.DataFrame:
        """
        统一产品指标查询（支持层级感知，避免重复计数）
        
        Args:
            platforms: 平台列表
            shops: 店铺列表
            skus: SKU列表
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            prefer_scope: 查询策略
                - 'auto': 优先商品级，缺失时聚合规格级（推荐，避免重复计数）
                - 'product': 仅商品级
                - 'variant': 仅规格级
                - 'both': 商品级+规格级（需自行处理重复计数）
            include_metadata: 是否包含metric_source/quality_score等元数据
        
        Returns:
            pd.DataFrame: 包含列
                - platform_code, shop_id, platform_sku, metric_date
                - sales_volume, sales_amount, page_views, unique_visitors, ...
                - [可选] metric_source (product|variant_agg|both)
                - [可选] sku_scope, parent_platform_sku
        """
        try:
            if prefer_scope == 'auto':
                # 策略：优先取product行；若某SKU无product行，则聚合其variant行
                sql = """
                WITH product_level AS (
                    SELECT * FROM fact_product_metrics
                    WHERE sku_scope = 'product'
                    {filters}
                ),
                variant_agg AS (
                    SELECT 
                        platform_code,
                        shop_id,
                        parent_platform_sku AS platform_sku,
                        metric_date,
                        granularity,
                        SUM(sales_volume) AS sales_volume,
                        SUM(sales_amount) AS sales_amount,
                        AVG(sales_amount_rmb) AS sales_amount_rmb,
                        SUM(page_views) AS page_views,
                        SUM(unique_visitors) AS unique_visitors,
                        SUM(add_to_cart_count) AS add_to_cart_count,
                        AVG(conversion_rate) AS conversion_rate,
                        'variant_agg' AS metric_source
                    FROM fact_product_metrics
                    WHERE sku_scope = 'variant'
                        AND parent_platform_sku IS NOT NULL
                        AND parent_platform_sku NOT IN (
                            SELECT DISTINCT platform_sku FROM product_level
                        )
                    {filters}
                    GROUP BY platform_code, shop_id, parent_platform_sku, metric_date, granularity
                )
                SELECT 
                    platform_code, shop_id, platform_sku, metric_date, granularity,
                    sales_volume, sales_amount, sales_amount_rmb,
                    page_views, unique_visitors, add_to_cart_count, conversion_rate,
                    'product' AS metric_source
                FROM product_level
                UNION ALL
                SELECT * FROM variant_agg
                ORDER BY metric_date DESC, sales_amount_rmb DESC NULLS LAST
                """
            elif prefer_scope == 'product':
                sql = """
                SELECT * FROM fact_product_metrics
                WHERE sku_scope = 'product'
                {filters}
                ORDER BY metric_date DESC, sales_amount_rmb DESC NULLS LAST
                """
            elif prefer_scope == 'variant':
                sql = """
                SELECT * FROM fact_product_metrics
                WHERE sku_scope = 'variant'
                {filters}
                ORDER BY metric_date DESC, parent_platform_sku, sales_amount_rmb DESC NULLS LAST
                """
            else:  # both
                sql = """
                SELECT * FROM fact_product_metrics
                WHERE 1=1
                {filters}
                ORDER BY metric_date DESC, sku_scope, sales_amount_rmb DESC NULLS LAST
                """
            
            # 构建过滤条件
            conditions = []
            params = {}
            
            if platforms:
                conditions.append("AND platform_code IN :platforms")
                params['platforms'] = tuple(platforms)
            if shops:
                conditions.append("AND shop_id IN :shops")
                params['shops'] = tuple(shops)
            if skus:
                conditions.append("AND platform_sku IN :skus")
                params['skus'] = tuple(skus)
            if start_date:
                conditions.append("AND metric_date >= :start_date")
                params['start_date'] = start_date
            if end_date:
                conditions.append("AND metric_date <= :end_date")
                params['end_date'] = end_date
            
            filters = " ".join(conditions) if conditions else ""
            final_sql = sql.format(filters=filters)
            
            with self._get_engine().connect() as conn:
                df = pd.read_sql_query(text(final_sql), conn, params=params)
            
            logger.info(f"[QueryService] 查询产品指标: {len(df)}条, prefer_scope={prefer_scope}")
            return df
            
        except Exception as e:
            logger.error(f"查询产品指标失败: {e}", exc_info=True)
            return pd.DataFrame()


# 全局实例
_data_query_service: Optional[DataQueryService] = None


def get_data_query_service() -> DataQueryService:
    """获取全局数据查询服务实例"""
    global _data_query_service
    if _data_query_service is None:
        _data_query_service = DataQueryService()
    return _data_query_service


# 便捷函数
def query_orders(**kwargs) -> pd.DataFrame:
    """便捷函数：查询订单"""
    return get_data_query_service().get_orders(**kwargs)


def query_product_metrics(**kwargs) -> pd.DataFrame:
    """便捷函数：查询产品指标"""
    return get_data_query_service().get_product_metrics(**kwargs)


def query_catalog_status() -> Dict[str, Any]:
    """便捷函数：查询Catalog状态"""
    return get_data_query_service().get_catalog_status()


if __name__ == '__main__':
    # 示例使用
    service = DataQueryService()
    
    # 查询订单
    print("查询订单...")
    orders = service.get_orders(
        platforms=['shopee'],
        start_date='2024-10-01',
        end_date='2024-10-16',
        limit=10
    )
    print(f"订单数: {len(orders)}")
    
    # 查询Top产品
    print("\nTop 5产品...")
    top = service.get_top_products(
        metric_type='gmv',
        start_date='2024-10-01',
        end_date='2024-10-16',
        top_n=5
    )
    print(f"Top产品数: {len(top)}")
    
    # Catalog状态
    print("\nCatalog状态...")
    status = service.get_catalog_status()
    print(f"总文件数: {status['total']}")

