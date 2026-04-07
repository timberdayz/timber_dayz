#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建缺失的物化视图（v4.11.2）

创建以下视图：
1. mv_top_products - TopN产品排行
2. mv_shop_product_summary - 店铺产品汇总
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import engine, SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def create_mv_top_products(db):
    """创建mv_top_products视图"""
    logger.info("=" * 70)
    logger.info("创建 mv_top_products 物化视图")
    logger.info("=" * 70)
    
    try:
        # 检查视图是否已存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' 
                AND matviewname = 'mv_top_products'
            )
        """))
        exists = result.scalar()
        
        if exists:
            logger.warning("mv_top_products 已存在，跳过创建")
            return True
        
        # 创建视图
        logger.info("创建 mv_top_products 视图...")
        db.execute(text("""
            CREATE MATERIALIZED VIEW mv_top_products AS
            SELECT 
                platform_code,
                shop_id,
                platform_sku,
                MAX(product_name) AS product_name,
                SUM(sales_volume) AS total_units,
                SUM(sales_amount_rmb) AS total_gmv_rmb,
                SUM(page_views) AS total_page_views,
                SUM(unique_visitors) AS total_visitors,
                AVG(conversion_rate) AS avg_conversion_rate,
                COUNT(DISTINCT metric_date) AS active_days,
                MAX(metric_date) AS last_metric_date
            FROM fact_product_metrics
            WHERE sku_scope = 'product'
              AND metric_date >= CURRENT_DATE - INTERVAL '30 days'
              AND sales_amount_rmb > 0
              AND COALESCE(data_domain, 'products') = 'products'
            GROUP BY platform_code, shop_id, platform_sku
            ORDER BY total_gmv_rmb DESC
            LIMIT 1000
        """))
        
        # 创建索引
        logger.info("创建 mv_top_products 索引...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_top_products_platform 
            ON mv_top_products(platform_code, shop_id)
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_top_products_gmv 
            ON mv_top_products(total_gmv_rmb DESC)
        """))
        
        db.commit()
        logger.info("[OK] mv_top_products 创建成功")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 创建 mv_top_products 失败: {e}", exc_info=True)
        return False


def create_mv_shop_product_summary(db):
    """创建mv_shop_product_summary视图"""
    logger.info("=" * 70)
    logger.info("创建 mv_shop_product_summary 物化视图")
    logger.info("=" * 70)
    
    try:
        # 检查视图是否已存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' 
                AND matviewname = 'mv_shop_product_summary'
            )
        """))
        exists = result.scalar()
        
        if exists:
            logger.warning("mv_shop_product_summary 已存在，跳过创建")
            return True
        
        # 检查mv_product_management是否存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' 
                AND matviewname = 'mv_product_management'
            )
        """))
        mv_exists = result.scalar()
        
        if not mv_exists:
            logger.error("[ERROR] mv_product_management 不存在，无法创建 mv_shop_product_summary")
            logger.error("请先创建 mv_product_management 视图")
            return False
        
        # 创建视图（基于mv_product_management）
        logger.info("创建 mv_shop_product_summary 视图（基于mv_product_management）...")
        db.execute(text("""
            CREATE MATERIALIZED VIEW mv_shop_product_summary AS
            SELECT 
                platform_code,
                platform_name,
                shop_id,
                shop_name,
                
                -- 产品数量统计
                COUNT(*) as total_products,
                COUNT(CASE WHEN stock_status = 'out_of_stock' THEN 1 END) as out_of_stock_count,
                COUNT(CASE WHEN stock_status = 'low_stock' THEN 1 END) as low_stock_count,
                COUNT(CASE WHEN stock_status = 'medium_stock' THEN 1 END) as medium_stock_count,
                COUNT(CASE WHEN stock_status = 'high_stock' THEN 1 END) as high_stock_count,
                
                -- 库存汇总
                SUM(COALESCE(stock, 0)) as total_stock,
                SUM(COALESCE(available_stock, 0)) as total_available_stock,
                SUM(COALESCE(reserved_stock, 0)) as total_reserved_stock,
                
                -- 销售汇总
                SUM(COALESCE(sales_volume, 0)) as total_sales_volume,
                SUM(COALESCE(sales_amount_rmb, 0)) as total_sales_amount_rmb,
                SUM(COALESCE(sales_volume_30d, 0)) as total_sales_volume_30d,
                
                -- 流量汇总
                SUM(COALESCE(page_views, 0)) as total_page_views,
                SUM(COALESCE(unique_visitors, 0)) as total_visitors,
                
                -- 平均指标
                AVG(COALESCE(price_rmb, 0)) as avg_price,
                AVG(COALESCE(conversion_rate, 0)) as avg_conversion_rate,
                AVG(COALESCE(product_health_score, 0)) as avg_health_score,
                AVG(COALESCE(rating, 0)) as avg_rating,
                
                -- 最值
                MAX(price_rmb) as max_price,
                MIN(price_rmb) as min_price,
                
                -- 分类统计
                COUNT(DISTINCT category) as category_count,
                
                -- 时间
                MAX(metric_date) as latest_date,
                MAX(updated_at) as last_updated
                
            FROM mv_product_management
            GROUP BY platform_code, platform_name, shop_id, shop_name
        """))
        
        # 创建索引
        logger.info("创建 mv_shop_product_summary 索引...")
        db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_summary_pk 
            ON mv_shop_product_summary(platform_code, shop_id)
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_shop_platform 
            ON mv_shop_product_summary(platform_code)
        """))
        
        db.commit()
        logger.info("[OK] mv_shop_product_summary 创建成功")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 创建 mv_shop_product_summary 失败: {e}", exc_info=True)
        return False


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("创建缺失的物化视图（v4.11.2）")
    logger.info("=" * 70)
    
    db = SessionLocal()
    try:
        success_count = 0
        
        # 创建mv_top_products
        if create_mv_top_products(db):
            success_count += 1
        
        # 创建mv_shop_product_summary
        if create_mv_shop_product_summary(db):
            success_count += 1
        
        logger.info("=" * 70)
        logger.info(f"完成: {success_count}/2 个视图创建成功")
        logger.info("=" * 70)
        
        if success_count == 2:
            logger.info("[OK] 所有缺失的物化视图已创建")
        else:
            logger.warning(f"[WARNING] {2 - success_count} 个视图创建失败")
        
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()

