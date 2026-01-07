#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查订单明细数据并更新物化视图
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

def check_and_fix_order_mv():
    safe_print("======================================================================")
    safe_print("检查订单明细数据并更新物化视图")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查fact_order_items表是否有数据
        safe_print("\n[1] 检查fact_order_items表的数据...")
        count = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_order_items
        """)).scalar()
        safe_print(f"  fact_order_items表总记录数: {count}条")
        
        if count > 0:
            # 检查tiktok的订单明细
            tiktok_count = db.execute(text("""
                SELECT COUNT(*) 
                FROM fact_order_items foi
                INNER JOIN fact_orders fo ON foi.order_id::text = fo.order_id
                WHERE fo.platform_code = 'tiktok'
            """)).scalar()
            safe_print(f"  tiktok订单明细数: {tiktok_count}条")
            
            # 显示示例数据
            if tiktok_count > 0:
                safe_print("\n  示例数据（前3条）:")
                samples = db.execute(text("""
                    SELECT 
                        foi.order_id,
                        foi.platform_sku,
                        foi.quantity,
                        foi.line_amount_cny,
                        fo.platform_code,
                        fo.shop_id
                    FROM fact_order_items foi
                    INNER JOIN fact_orders fo ON foi.order_id::text = fo.order_id
                    WHERE fo.platform_code = 'tiktok'
                    LIMIT 3
                """)).fetchall()
                for s in samples:
                    safe_print(f"    order_id={s[0]}, platform_sku={s[1]}, quantity={s[2]}, amount={s[3]}")
        
        # 2. 检查fact_orders表的数据
        safe_print("\n[2] 检查fact_orders表的数据...")
        tiktok_orders = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        safe_print(f"  tiktok订单数: {tiktok_orders}条")
        
        # 3. 检查当前物化视图的数据
        safe_print("\n[3] 检查当前物化视图的数据...")
        mv_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_day_shop_sku 
            WHERE platform_code = 'tiktok'
        """)).scalar()
        safe_print(f"  mv_sales_day_shop_sku中tiktok数据数: {mv_count}条")
        
        # 检查是否有非0的sales_amount_cny
        non_zero_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_day_shop_sku 
            WHERE platform_code = 'tiktok' 
              AND sales_amount_cny > 0
        """)).scalar()
        safe_print(f"  其中sales_amount_cny > 0的记录数: {non_zero_count}条")
        
        # 4. 如果fact_order_items有数据，更新物化视图
        if count > 0:
            safe_print("\n[4] fact_order_items表有数据，更新物化视图...")
            safe_print("  删除旧的物化视图...")
            db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_sales_day_shop_sku CASCADE"))
            db.commit()
            
            safe_print("  创建新的物化视图（基于fact_order_items）...")
            create_sql = """
            CREATE MATERIALIZED VIEW mv_sales_day_shop_sku AS
            SELECT 
                fo.platform_code,
                fo.shop_id,
                foi.platform_sku,
                COALESCE(fo.order_date_local, DATE(fo.order_time_utc)) AS sale_date,
                
                -- 销售指标
                COUNT(DISTINCT fo.order_id) AS order_count,
                SUM(foi.quantity) AS units_sold,
                SUM(foi.line_amount_cny) AS sales_amount_cny,
                SUM(foi.line_amount) AS sales_amount,
                
                -- 平均指标
                AVG(foi.unit_price_cny) AS avg_unit_price_cny,
                
                -- 元数据
                MAX(foi.product_name) AS product_title,
                MAX(fo.currency) AS currency,
                
                -- 时间戳
                CURRENT_TIMESTAMP AS refreshed_at
            FROM 
                fact_order_items foi
                INNER JOIN fact_orders fo ON (
                    foi.order_id::text = fo.order_id
                )
            WHERE 
                COALESCE(fo.is_cancelled, false) = false
                AND (fo.order_date_local IS NOT NULL OR fo.order_time_utc IS NOT NULL)
            GROUP BY 
                fo.platform_code,
                fo.shop_id,
                foi.platform_sku,
                COALESCE(fo.order_date_local, DATE(fo.order_time_utc));
            
            -- 创建索引
            CREATE INDEX IF NOT EXISTS idx_mv_sales_shop_date ON mv_sales_day_shop_sku(platform_code, shop_id, sale_date);
            CREATE INDEX IF NOT EXISTS idx_mv_sales_sku_date ON mv_sales_day_shop_sku(platform_sku, sale_date);
            CREATE INDEX IF NOT EXISTS idx_mv_sales_date ON mv_sales_day_shop_sku(sale_date DESC);
            
            COMMENT ON MATERIALIZED VIEW mv_sales_day_shop_sku IS '日粒度销售聚合视图（从订单明细聚合），用于TopN分析与P&L';
            """
            
            db.execute(text(create_sql))
            db.commit()
            safe_print("  [OK] 物化视图已更新")
            
            # 5. 检查更新后的数据
            safe_print("\n[5] 检查更新后的数据...")
            mv_count = db.execute(text("""
                SELECT COUNT(*) 
                FROM mv_sales_day_shop_sku 
                WHERE platform_code = 'tiktok'
            """)).scalar()
            safe_print(f"  mv_sales_day_shop_sku中tiktok数据数: {mv_count}条")
            
            non_zero_count = db.execute(text("""
                SELECT COUNT(*) 
                FROM mv_sales_day_shop_sku 
                WHERE platform_code = 'tiktok' 
                  AND sales_amount_cny > 0
            """)).scalar()
            safe_print(f"  其中sales_amount_cny > 0的记录数: {non_zero_count}条")
            
            # 显示示例数据
            if mv_count > 0:
                safe_print("\n  示例数据（前5条）:")
                samples = db.execute(text("""
                    SELECT 
                        platform_code,
                        shop_id,
                        platform_sku,
                        sale_date,
                        order_count,
                        units_sold,
                        sales_amount_cny
                    FROM mv_sales_day_shop_sku 
                    WHERE platform_code = 'tiktok'
                    ORDER BY sale_date DESC
                    LIMIT 5
                """)).fetchall()
                for s in samples:
                    safe_print(f"    {s[0]} | {s[1]} | SKU={s[2]} | 日期={s[3]} | 订单数={s[4]} | 数量={s[5]} | 金额={s[6]:.2f}元")
        else:
            safe_print("\n[4] fact_order_items表为空，无法更新物化视图")
            safe_print("  问题: 订单明细数据未入库")
            safe_print("  原因: 订单数据入库逻辑只入库订单级别数据，未入库订单明细")
            safe_print("  解决方案: 需要完善订单明细入库逻辑")
        
        safe_print("\n======================================================================")
        safe_print("检查完成")
        safe_print("======================================================================")
        
    except Exception as e:
        db.rollback()
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_and_fix_order_mv()

