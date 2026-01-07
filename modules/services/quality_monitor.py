#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量监控服务

功能：
- 检测orders与products的GMV差异
- 生成质量告警
- 写入quality_reports表
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from modules.core.logger import get_logger

logger = get_logger(__name__)


def detect_gmv_conflicts(
    engine,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    threshold: float = 0.05  # 5%偏差阈值
) -> List[Dict]:
    """
    检测orders与products的GMV冲突
    
    Args:
        engine: 数据库引擎
        start_date: 开始日期（默认最近30天）
        end_date: 结束日期（默认今天）
        threshold: 偏差阈值（默认5%）
    
    Returns:
        List[Dict]: 冲突列表
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    sql = """
    WITH orders_gmv AS (
        SELECT 
            platform_code,
            shop_id,
            order_date_local AS metric_date,
            SUM(total_amount_rmb) AS gmv_from_orders,
            COUNT(DISTINCT order_id) AS order_count
        FROM fact_orders
        WHERE order_date_local >= :start_date
          AND order_date_local <= :end_date
          AND total_amount_rmb > 0
        GROUP BY platform_code, shop_id, order_date_local
    ),
    products_gmv AS (
        SELECT 
            platform_code,
            shop_id,
            metric_date,
            SUM(sales_amount_rmb) AS gmv_from_products
        FROM fact_product_metrics
        WHERE sku_scope = 'product'
          AND metric_date >= :start_date
          AND metric_date <= :end_date
          AND sales_amount_rmb > 0
        GROUP BY platform_code, shop_id, metric_date
    ),
    combined AS (
        SELECT 
            COALESCE(o.platform_code, p.platform_code) AS platform_code,
            COALESCE(o.shop_id, p.shop_id) AS shop_id,
            COALESCE(o.metric_date, p.metric_date) AS metric_date,
            COALESCE(o.gmv_from_orders, 0) AS gmv_from_orders,
            COALESCE(p.gmv_from_products, 0) AS gmv_from_products,
            COALESCE(o.order_count, 0) AS order_count
        FROM orders_gmv o
        LEFT JOIN products_gmv p
          ON o.platform_code = p.platform_code
          AND o.shop_id = p.shop_id
          AND o.metric_date = p.metric_date
        UNION
        SELECT 
            p.platform_code,
            p.shop_id,
            p.metric_date,
            COALESCE(o.gmv_from_orders, 0) AS gmv_from_orders,
            COALESCE(p.gmv_from_products, 0) AS gmv_from_products,
            COALESCE(o.order_count, 0) AS order_count
        FROM products_gmv p
        LEFT JOIN orders_gmv o
          ON o.platform_code = p.platform_code
          AND o.shop_id = p.shop_id
          AND o.metric_date = p.metric_date
        WHERE o.platform_code IS NULL
    )
    SELECT 
        platform_code,
        shop_id,
        metric_date,
        gmv_from_orders,
        gmv_from_products,
        order_count,
        ABS(gmv_from_orders - gmv_from_products) AS diff_abs,
        ABS(gmv_from_orders - gmv_from_products) / 
            NULLIF(
                CASE 
                    WHEN gmv_from_orders > gmv_from_products 
                    THEN gmv_from_orders 
                    ELSE gmv_from_products 
                END, 
                0
            ) AS deviation
    FROM combined
    WHERE ABS(gmv_from_orders - gmv_from_products) /
            NULLIF(
                CASE 
                    WHEN gmv_from_orders > gmv_from_products 
                    THEN gmv_from_orders 
                    ELSE gmv_from_products 
                END, 
                0
            ) > :threshold
    ORDER BY deviation DESC
    """
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(
                text(sql),
                conn,
                params={
                    'start_date': start_date,
                    'end_date': end_date,
                    'threshold': threshold
                }
            )
        
        conflicts = df.to_dict('records')
        logger.info(f"[QualityMonitor] 发现{len(conflicts)}个GMV冲突（偏差>{threshold*100}%）")
        return conflicts
        
    except Exception as e:
        logger.error(f"GMV冲突检测失败: {e}", exc_info=True)
        return []


def generate_quality_report(engine) -> Dict:
    """
    生成完整质量报告
    
    Returns:
        Dict: 质量报告
    """
    conflicts = detect_gmv_conflicts(engine)
    
    # 分级统计
    high_risk = [c for c in conflicts if c.get('deviation', 0) > 0.10]  # >10%
    medium_risk = [c for c in conflicts if 0.05 < c.get('deviation', 0) <= 0.10]  # 5-10%
    
    report = {
        'total_conflicts': len(conflicts),
        'high_risk': len(high_risk),
        'medium_risk': len(medium_risk),
        'conflicts': conflicts[:20],  # 最严重的20个
        'generated_at': datetime.utcnow().isoformat()
    }
    
    logger.info(f"[QualityMonitor] 质量报告: {report['total_conflicts']}个冲突, 高风险{report['high_risk']}个")
    return report

