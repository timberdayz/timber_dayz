#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建mv_product_management物化视图（修复版）
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def create_mv_product_management():
    """创建mv_product_management物化视图"""
    db = next(get_db())
    try:
        safe_print("\n" + "="*70)
        safe_print("创建mv_product_management物化视图")
        safe_print("="*70)
        
        # Step 1: 删除旧视图（如果存在）
        safe_print("\n[Step 1] 删除旧视图...")
        try:
            db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_product_management CASCADE"))
            db.commit()
            safe_print("[OK] 旧视图已删除")
        except Exception as e:
            safe_print(f"[WARN] 删除旧视图警告: {e}")
            db.rollback()
        
        # Step 2: 创建物化视图（只创建视图本身，不包括函数）
        safe_print("\n[Step 2] 创建物化视图...")
        create_mv_sql = """
        CREATE MATERIALIZED VIEW mv_product_management AS
        SELECT 
            -- ========== 主键和标识 ==========
            p.id as metric_id,
            p.platform_code,
            plat.name as platform_name,
            p.shop_id,
            s.shop_name,
            
            -- ========== 产品基本信息 ==========
            p.platform_sku,
            p.product_name,
            p.category,
            p.brand,
            p.specification,
            p.image_url,
            p.sku_scope,
            p.parent_platform_sku,
            
            -- ========== 价格信息 ==========
            p.price,
            p.currency,
            p.price_rmb,
            
            -- ========== 库存信息（v4.6.3细分） ==========
            p.stock,
            p.total_stock,
            p.available_stock,
            p.reserved_stock,
            p.in_transit_stock,
            p.warehouse,
            
            -- 计算字段：库存状态（业务逻辑集中管理）
            CASE 
                WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
                ELSE 'high_stock'
            END as stock_status,
            
            -- ========== 销售指标 ==========
            p.sales_volume,
            p.sales_amount,
            p.sales_amount_rmb,
            p.sales_volume_7d,
            p.sales_volume_30d,
            p.sales_volume_60d,
            p.sales_volume_90d,
            
            -- ========== 流量指标 ==========
            p.page_views,
            p.unique_visitors,
            p.click_through_rate,
            p.order_count,
            
            -- ========== 转化指标 ==========
            p.conversion_rate,
            p.add_to_cart_count,
            
            -- 计算字段：转化率（如果没有则计算）
            CASE 
                WHEN p.conversion_rate IS NOT NULL THEN p.conversion_rate
                WHEN COALESCE(p.page_views, 0) > 0 
                THEN ROUND((p.sales_volume::numeric / p.page_views * 100), 2)
                ELSE 0
            END as conversion_rate_calc,
            
            -- 计算字段：加购率
            CASE 
                WHEN COALESCE(p.page_views, 0) > 0 
                THEN ROUND((p.add_to_cart_count::numeric / p.page_views * 100), 2)
                ELSE 0
            END as add_to_cart_rate,
            
            -- ========== 评价指标 ==========
            p.rating,
            p.review_count,
            
            -- ========== 时间维度 ==========
            p.metric_date,
            p.granularity,
            p.period_start,
            p.metric_date_utc,
            
            -- ========== 计算字段（业务价值）==========
            -- 预估营收（CNY）
            p.sales_volume * COALESCE(p.price_rmb, p.price, 0) as estimated_revenue_rmb,
            
            -- 库存周转天数（基于30天销量）
            CASE 
                WHEN COALESCE(p.sales_volume_30d, p.sales_volume, 0) > 0 
                THEN ROUND((COALESCE(p.available_stock, p.stock, 0)::numeric / (p.sales_volume_30d::numeric / 30)), 1)
                ELSE 999
            END as inventory_turnover_days,
            
            -- 产品健康度评分（0-100）
            LEAST(100, GREATEST(0,
                COALESCE(p.rating, 0) * 20 +  -- 评分占20分
                CASE WHEN COALESCE(p.stock, 0) > 0 THEN 20 ELSE 0 END +  -- 有库存20分
                LEAST(20, COALESCE(p.sales_volume, 0) / 10) +  -- 销量占20分
                LEAST(20, COALESCE(p.page_views, 0) / 100) +  -- 流量占20分
                CASE WHEN COALESCE(p.conversion_rate, 0) > 1 THEN 20 ELSE 0 END  -- 有转化20分
            )) as product_health_score,
            
            -- ========== 审计字段 ==========
            p.source_catalog_id,
            p.created_at,
            p.updated_at
            
        FROM fact_product_metrics p
        LEFT JOIN dim_platforms plat ON p.platform_code = plat.platform_code
        LEFT JOIN dim_shops s ON p.platform_code = s.platform_code AND p.shop_id = s.shop_id
        
        -- v4.10.0更新：只包含products域数据（商品销售表现）
        -- ⚠️ 注意：inventory域数据应使用mv_inventory_by_sku视图
        -- 性能优化：只保留最近90天数据
        WHERE p.metric_date >= CURRENT_DATE - INTERVAL '90 days'
          AND COALESCE(p.data_domain, 'products') = 'products'  -- 只查询products域
        
        WITH DATA;
        """
        
        db.execute(text(create_mv_sql))
        db.commit()
        safe_print("[OK] 物化视图已创建")
        
        # Step 3: 创建唯一索引（必须有，支持CONCURRENTLY刷新）
        safe_print("\n[Step 3] 创建唯一索引...")
        indexes = [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_product_management_pk ON mv_product_management(metric_id);",
            "CREATE INDEX IF NOT EXISTS idx_mv_product_platform ON mv_product_management(platform_code);",
            "CREATE INDEX IF NOT EXISTS idx_mv_product_category ON mv_product_management(category);",
            "CREATE INDEX IF NOT EXISTS idx_mv_product_stock_status ON mv_product_management(stock_status);",
            "CREATE INDEX IF NOT EXISTS idx_mv_product_date ON mv_product_management(metric_date DESC);",
            "CREATE INDEX IF NOT EXISTS idx_mv_product_platform_sku ON mv_product_management(platform_code, platform_sku);"
        ]
        
        for idx_sql in indexes:
            try:
                db.execute(text(idx_sql))
                db.commit()
            except Exception as e:
                safe_print(f"[WARN] 创建索引警告: {e}")
                db.rollback()
        
        safe_print("[OK] 索引创建完成")
        
        # Step 4: 验证视图
        safe_print("\n[Step 4] 验证视图...")
        count_result = db.execute(text("SELECT COUNT(*) FROM mv_product_management")).scalar()
        safe_print(f"[OK] 物化视图包含 {count_result} 行数据")
        
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] mv_product_management物化视图创建成功！")
        safe_print("="*70)
        
        return True
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 创建物化视图失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    create_mv_product_management()

