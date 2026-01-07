#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查订单表关联和数据
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

def check_order_tables():
    safe_print("======================================================================")
    safe_print("检查订单表关联和数据")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查fact_orders表的数据
        safe_print("\n[1] 检查fact_orders表的数据...")
        result = db.execute(text("""
            SELECT platform_code, COUNT(*) as cnt, MIN(order_id) as sample_order_id
            FROM fact_orders 
            WHERE platform_code IN ('tiktok', 'shopee')
            GROUP BY platform_code
        """)).fetchall()
        for r in result:
            safe_print(f"  {r[0]}: {r[1]}条订单, 示例order_id: {r[2]}")
        
        # 2. 检查fact_order_items表的数据
        safe_print("\n[2] 检查fact_order_items表的数据...")
        result = db.execute(text("""
            SELECT COUNT(*) as cnt, MIN(order_id) as sample_order_id, MAX(order_id) as max_order_id
            FROM fact_order_items
            LIMIT 1
        """)).fetchone()
        if result:
            safe_print(f"  总订单明细数: {result[0]}条")
            safe_print(f"  示例order_id: {result[1]} (类型: {type(result[1])})")
            safe_print(f"  最大order_id: {result[2]}")
        
        # 3. 检查关联是否成功
        safe_print("\n[3] 检查表关联...")
        result = db.execute(text("""
            SELECT COUNT(*) as cnt
            FROM fact_order_items foi
            INNER JOIN fact_orders fo ON foi.order_id::text = fo.order_id
            WHERE fo.platform_code IN ('tiktok', 'shopee')
        """)).scalar()
        safe_print(f"  关联成功的记录数: {result}条")
        
        # 4. 检查order_id的数据类型和格式
        safe_print("\n[4] 检查order_id的数据类型和格式...")
        result = db.execute(text("""
            SELECT 
                pg_typeof(order_id) as foi_type,
                pg_typeof((SELECT order_id FROM fact_orders LIMIT 1)) as fo_type
            FROM fact_order_items
            LIMIT 1
        """)).fetchone()
        if result:
            safe_print(f"  fact_order_items.order_id类型: {result[0]}")
            safe_print(f"  fact_orders.order_id类型: {result[1]}")
        
        # 5. 检查order_id的示例值
        safe_print("\n[5] 检查order_id的示例值...")
        foi_sample = db.execute(text("""
            SELECT order_id, platform_sku 
            FROM fact_order_items 
            LIMIT 5
        """)).fetchall()
        safe_print("  fact_order_items示例:")
        for r in foi_sample:
            safe_print(f"    order_id={r[0]} (类型: {type(r[0])}), platform_sku={r[1]}")
        
        fo_sample = db.execute(text("""
            SELECT order_id, platform_code 
            FROM fact_orders 
            WHERE platform_code IN ('tiktok', 'shopee')
            LIMIT 5
        """)).fetchall()
        safe_print("  fact_orders示例:")
        for r in fo_sample:
            safe_print(f"    order_id={r[0]} (类型: {type(r[0])}), platform_code={r[1]}")
        
        safe_print("\n======================================================================")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_order_tables()

