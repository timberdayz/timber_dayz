#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查订单数据域的物化视图
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

def check_materialized_views():
    safe_print("======================================================================")
    safe_print("检查订单数据域的物化视图")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查所有物化视图
        safe_print("\n[1] 数据库中所有物化视图:")
        result = db.execute(text("""
            SELECT schemaname, matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public' 
            ORDER BY matviewname
        """)).fetchall()
        for r in result:
            safe_print(f"  - {r[1]}")
        
        # 2. 检查mv_sales_day_shop_sku是否存在
        safe_print("\n[2] 检查mv_sales_day_shop_sku视图:")
        try:
            count = db.execute(text("""
                SELECT COUNT(*) 
                FROM mv_sales_day_shop_sku 
                WHERE platform_code IN ('tiktok', 'shopee')
            """)).scalar()
            safe_print(f"  [OK] 视图存在，tiktok和shopee订单数据数: {count}")
            
            # 检查具体平台数据
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
        except Exception as e:
            safe_print(f"  [FAIL] 视图不存在或查询失败: {e}")
        
        # 3. 检查mv_daily_sales是否存在
        safe_print("\n[3] 检查mv_daily_sales视图:")
        try:
            count = db.execute(text("""
                SELECT COUNT(*) 
                FROM mv_daily_sales 
                WHERE platform_code IN ('tiktok', 'shopee')
            """)).scalar()
            safe_print(f"  [OK] 视图存在，tiktok和shopee订单数据数: {count}")
        except Exception as e:
            safe_print(f"  [FAIL] 视图不存在或查询失败: {e}")
        
        # 4. 检查fact_orders表中的订单数据
        safe_print("\n[4] 检查fact_orders表中的订单数据:")
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
        safe_print(f"  - tiktok订单数: {tiktok_orders}条")
        safe_print(f"  - shopee订单数: {shopee_orders}条")
        
        # 5. 检查fact_order_items表中的订单明细数据
        safe_print("\n[5] 检查fact_order_items表中的订单明细数据:")
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
        safe_print(f"  - tiktok订单明细数: {tiktok_items}条")
        safe_print(f"  - shopee订单明细数: {shopee_items}条")
        
        safe_print("\n======================================================================")
        safe_print("检查完成")
        safe_print("======================================================================")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_materialized_views()

