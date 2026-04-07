#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查fact_order_items表结构并创建订单物化视图
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

def check_and_create_order_views():
    safe_print("======================================================================")
    safe_print("检查表结构并创建订单物化视图")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查fact_order_items表结构
        safe_print("\n[1] 检查fact_order_items表结构...")
        columns = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'fact_order_items' 
            ORDER BY ordinal_position
        """)).fetchall()
        safe_print("  fact_order_items表字段:")
        for col in columns:
            safe_print(f"    - {col[0]} ({col[1]})")
        
        # 2. 检查fact_orders表结构
        safe_print("\n[2] 检查fact_orders表结构...")
        columns = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'fact_orders' 
            ORDER BY ordinal_position
            LIMIT 20
        """)).fetchall()
        safe_print("  fact_orders表字段（前20个）:")
        for col in columns:
            safe_print(f"    - {col[0]} ({col[1]})")
        
        # 3. 检查订单数据
        safe_print("\n[3] 检查订单数据...")
        tiktok_orders = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        shopee_orders = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_orders 
            WHERE platform_code = 'shopee'
        """)).scalar()
        safe_print(f"  tiktok订单数: {tiktok_orders}条")
        safe_print(f"  shopee订单数: {shopee_orders}条")
        
        # 4. 检查订单明细数据
        safe_print("\n[4] 检查订单明细数据...")
        tiktok_items = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_order_items 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        shopee_items = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_order_items 
            WHERE platform_code = 'shopee'
        """)).scalar()
        safe_print(f"  tiktok订单明细数: {tiktok_items}条")
        safe_print(f"  shopee订单明细数: {shopee_items}条")
        
        # 5. 创建订单物化视图（基于实际表结构）
        safe_print("\n[5] 创建订单物化视图...")
        create_sql = """
        DROP MATERIALIZED VIEW IF EXISTS mv_sales_day_shop_sku CASCADE;
        
        CREATE MATERIALIZED VIEW mv_sales_day_shop_sku AS
        SELECT 
            fo.platform_code,
            fo.shop_id,
            foi.platform_sku,
            fo.order_date_local AS sale_date,
            
            -- 销售指标
            COUNT(DISTINCT fo.order_id) AS order_count,
            SUM(foi.quantity) AS units_sold,
            SUM(foi.line_amount) AS sales_amount,
            SUM(foi.line_amount_rmb) AS sales_amount_cny,
            
            -- 平均指标
            AVG(foi.unit_price_rmb) AS avg_unit_price_cny,
            
            -- 元数据
            MAX(foi.product_title) AS product_title,
            MAX(fo.currency) AS currency,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
        FROM 
            fact_order_items foi
            INNER JOIN fact_orders fo ON (
                foi.platform_code = fo.platform_code AND 
                foi.shop_id = fo.shop_id AND 
                foi.order_id = fo.order_id
            )
        WHERE 
            fo.is_cancelled = false
            AND fo.order_date_local IS NOT NULL
        GROUP BY 
            fo.platform_code,
            fo.shop_id,
            foi.platform_sku,
            fo.order_date_local;
        
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_mv_sales_shop_date ON mv_sales_day_shop_sku(platform_code, shop_id, sale_date);
        CREATE INDEX IF NOT EXISTS idx_mv_sales_sku_date ON mv_sales_day_shop_sku(platform_sku, sale_date);
        CREATE INDEX IF NOT EXISTS idx_mv_sales_date ON mv_sales_day_shop_sku(sale_date DESC);
        
        COMMENT ON MATERIALIZED VIEW mv_sales_day_shop_sku IS '日粒度销售聚合视图（从订单明细聚合），用于TopN分析与P&L';
        """
        
        db.execute(text(create_sql))
        db.commit()
        safe_print("  [OK] mv_sales_day_shop_sku视图创建成功")
        
        # 6. 检查视图中的数据
        safe_print("\n[6] 检查视图中的数据...")
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
        safe_print(f"操作失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_and_create_order_views()

