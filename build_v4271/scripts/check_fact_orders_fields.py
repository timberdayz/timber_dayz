#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查fact_orders表的数据和字段
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

def check_fact_orders_data():
    safe_print("======================================================================")
    safe_print("检查fact_orders表的数据和字段")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查fact_orders表的字段
        safe_print("\n[1] 检查fact_orders表的字段...")
        columns = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'fact_orders' 
            ORDER BY ordinal_position
        """)).fetchall()
        safe_print("  fact_orders表字段:")
        for col in columns:
            safe_print(f"    - {col[0]} ({col[1]}, nullable={col[2]})")
        
        # 2. 检查订单数据
        safe_print("\n[2] 检查订单数据...")
        result = db.execute(text("""
            SELECT 
                platform_code,
                COUNT(*) as cnt,
                COUNT(order_date_local) as has_date,
                COUNT(CASE WHEN is_cancelled = false THEN 1 END) as not_cancelled
            FROM fact_orders 
            WHERE platform_code IN ('tiktok', 'shopee')
            GROUP BY platform_code
        """)).fetchall()
        for r in result:
            safe_print(f"  {r[0]}: 总订单数={r[1]}, 有日期={r[2]}, 未取消={r[3]}")
        
        # 3. 检查order_date_local字段的值
        safe_print("\n[3] 检查order_date_local字段的值...")
        result = db.execute(text("""
            SELECT 
                platform_code,
                order_date_local,
                COUNT(*) as cnt
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            GROUP BY platform_code, order_date_local
            ORDER BY order_date_local DESC
            LIMIT 10
        """)).fetchall()
        safe_print("  tiktok订单日期分布（前10个）:")
        for r in result:
            safe_print(f"    {r[0]} | {r[1]} | {r[2]}条")
        
        # 4. 检查is_cancelled字段的值
        safe_print("\n[4] 检查is_cancelled字段的值...")
        result = db.execute(text("""
            SELECT 
                platform_code,
                is_cancelled,
                COUNT(*) as cnt
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            GROUP BY platform_code, is_cancelled
        """)).fetchall()
        safe_print("  tiktok订单is_cancelled分布:")
        for r in result:
            safe_print(f"    {r[0]} | is_cancelled={r[1]} | {r[2]}条")
        
        # 5. 检查物化视图查询条件
        safe_print("\n[5] 检查物化视图查询条件...")
        count = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_orders
            WHERE is_cancelled = false
              AND order_date_local IS NOT NULL
              AND platform_code IN ('tiktok', 'shopee')
        """)).scalar()
        safe_print(f"  符合物化视图条件的订单数: {count}条")
        
        safe_print("\n======================================================================")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_fact_orders_data()

