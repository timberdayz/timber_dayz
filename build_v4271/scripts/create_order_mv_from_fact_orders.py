#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建基于fact_orders表的订单物化视图
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

def create_order_mv_from_fact_orders():
    safe_print("======================================================================")
    safe_print("创建基于fact_orders表的订单物化视图")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 创建订单销售汇总视图（基于fact_orders表）
        safe_print("\n[1] 创建mv_order_sales_summary视图...")
        create_sql = """
        DROP MATERIALIZED VIEW IF EXISTS mv_order_sales_summary CASCADE;
        
        CREATE MATERIALIZED VIEW mv_order_sales_summary AS
        SELECT 
            platform_code,
            shop_id,
            COALESCE(order_date_local, DATE(order_time_utc)) AS sale_date,
            
            -- 订单统计
            COUNT(DISTINCT order_id) AS order_count,
            SUM(total_amount_rmb) AS total_gmv_rmb,
            SUM(total_amount) AS total_gmv,
            SUM(subtotal_rmb) AS total_subtotal_rmb,
            SUM(shipping_fee_rmb) AS total_shipping_fee_rmb,
            SUM(tax_amount_rmb) AS total_tax_rmb,
            SUM(discount_amount_rmb) AS total_discount_rmb,
            
            -- 平均指标
            AVG(total_amount_rmb) AS avg_order_value_rmb,
            
            -- 元数据
            MAX(currency) AS currency,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
        FROM fact_orders
        WHERE COALESCE(is_cancelled, false) = false
          AND (order_date_local IS NOT NULL OR order_time_utc IS NOT NULL)
        GROUP BY 
            platform_code,
            shop_id,
            COALESCE(order_date_local, DATE(order_time_utc));
        
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_mv_order_sales_platform_date ON mv_order_sales_summary(platform_code, shop_id, sale_date);
        CREATE INDEX IF NOT EXISTS idx_mv_order_sales_date ON mv_order_sales_summary(sale_date DESC);
        
        COMMENT ON MATERIALIZED VIEW mv_order_sales_summary IS '订单销售汇总视图（基于fact_orders表），用于订单趋势分析';
        """
        
        db.execute(text(create_sql))
        db.commit()
        safe_print("  [OK] mv_order_sales_summary视图创建成功")
        
        # 检查视图中的数据
        safe_print("\n[2] 检查视图中的数据...")
        count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_order_sales_summary 
            WHERE platform_code IN ('tiktok', 'shopee')
        """)).scalar()
        safe_print(f"  tiktok和shopee订单数据数: {count}")
        
        tiktok_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_order_sales_summary 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        shopee_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_order_sales_summary 
            WHERE platform_code = 'shopee'
        """)).scalar()
        safe_print(f"    - tiktok订单数据: {tiktok_count}条")
        safe_print(f"    - shopee订单数据: {shopee_count}条")
        
        # 显示示例数据
        safe_print("\n[3] 显示示例数据（前5条）...")
        samples = db.execute(text("""
            SELECT platform_code, shop_id, sale_date, order_count, total_gmv_rmb
            FROM mv_order_sales_summary 
            WHERE platform_code = 'tiktok'
            ORDER BY sale_date DESC
            LIMIT 5
        """)).fetchall()
        for s in samples:
            safe_print(f"    {s[0]} | {s[1]} | {s[2]} | 订单数:{s[3]} | GMV:{s[4]:.2f}元")
        
        safe_print("\n======================================================================")
        safe_print("[SUCCESS] 订单数据域物化视图创建完成！")
        safe_print("======================================================================")
        safe_print("\n总结:")
        safe_print("  - mv_order_sales_summary: 订单销售汇总视图（基于fact_orders表）")
        safe_print("  - 包含tiktok和shopee的订单数据")
        safe_print("  - 可以用于订单趋势分析和销售看板")
        
    except Exception as e:
        db.rollback()
        safe_print(f"创建失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_order_mv_from_fact_orders()

