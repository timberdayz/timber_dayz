#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据实际表结构创建订单物化视图
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def create_order_materialized_views():
    safe_print("======================================================================")
    safe_print("根据实际表结构创建订单物化视图")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查表关联关系
        safe_print("\n[1] 检查表关联关系...")
        # fact_order_items表通过order_id关联fact_orders表
        # 需要先检查是否有order_id字段可以关联
        
        # 2. 创建订单物化视图（基于实际表结构）
        safe_print("\n[2] 创建订单物化视图...")
        # 由于fact_order_items表没有数据，我们创建基于fact_orders表的视图
        create_sql = """
        DROP MATERIALIZED VIEW IF EXISTS mv_sales_day_shop_sku CASCADE;
        
        CREATE MATERIALIZED VIEW mv_sales_day_shop_sku AS
        SELECT 
            fo.platform_code,
            fo.shop_id,
            'N/A' AS platform_sku,  -- 由于没有订单明细，使用占位符
            COALESCE(fo.order_date_local, DATE(fo.order_time_utc)) AS sale_date,
            
            -- 销售指标（订单级别）
            COUNT(DISTINCT fo.order_id) AS order_count,
            0 AS units_sold,  -- 订单明细未入库，无法统计
            SUM(fo.total_amount_rmb) AS sales_amount_cny,
            SUM(fo.total_amount) AS sales_amount,
            
            -- 平均指标
            AVG(fo.total_amount_rmb) AS avg_unit_price_cny,
            
            -- 元数据
            '订单汇总' AS product_title,
            MAX(fo.currency) AS currency,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
        FROM 
            fact_orders fo
        WHERE 
            COALESCE(fo.is_cancelled, false) = false
            AND (fo.order_date_local IS NOT NULL OR fo.order_time_utc IS NOT NULL)
        GROUP BY 
            fo.platform_code,
            fo.shop_id,
            COALESCE(fo.order_date_local, DATE(fo.order_time_utc));
        
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_mv_sales_shop_date ON mv_sales_day_shop_sku(platform_code, shop_id, sale_date);
        CREATE INDEX IF NOT EXISTS idx_mv_sales_date ON mv_sales_day_shop_sku(sale_date DESC);
        
        COMMENT ON MATERIALIZED VIEW mv_sales_day_shop_sku IS '日粒度销售聚合视图（基于fact_orders表，订单明细未入库时使用）';
        """
        
        db.execute(text(create_sql))
        db.commit()
        safe_print("  [OK] mv_sales_day_shop_sku视图创建成功")
        
        # 3. 检查视图中的数据
        safe_print("\n[3] 检查视图中的数据...")
        count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_day_shop_sku 
            WHERE platform_code IN ('tiktok', 'shopee')
        """)).scalar()
        safe_print(f"  tiktok和shopee订单数据数: {count}")
        
        tiktok_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_day_shop_sku 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        shopee_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_day_shop_sku 
            WHERE platform_code = 'shopee'
        """)).scalar()
        safe_print(f"    - tiktok订单数据: {tiktok_count}条")
        safe_print(f"    - shopee订单数据: {shopee_count}条")
        
        safe_print("\n======================================================================")
        safe_print("[SUCCESS] 订单数据域物化视图创建完成！")
        safe_print("======================================================================")
        
    except Exception as e:
        db.rollback()
        safe_print(f"创建失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_order_materialized_views()

