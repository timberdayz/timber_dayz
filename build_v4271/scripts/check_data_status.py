#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据情况并修复物化视图
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

def check_data():
    """检查数据情况"""
    db = next(get_db())
    try:
        safe_print("\n" + "="*70)
        safe_print("检查数据情况")
        safe_print("="*70)
        
        # 检查数据域分布
        safe_print("\n[1] 数据域分布:")
        result = db.execute(text("""
            SELECT 
                COALESCE(data_domain, 'NULL') as domain,
                COUNT(*) as cnt
            FROM fact_product_metrics
            GROUP BY COALESCE(data_domain, 'NULL')
            ORDER BY cnt DESC
        """)).fetchall()
        
        for r in result:
            safe_print(f"  {r[0]}: {r[1]}条")
        
        # 检查products域数据日期范围
        safe_print("\n[2] products域数据日期范围:")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as cnt,
                MIN(metric_date) as min_date,
                MAX(metric_date) as max_date
            FROM fact_product_metrics
            WHERE COALESCE(data_domain, 'products') = 'products'
        """)).fetchone()
        
        if result and result[0] > 0:
            safe_print(f"  数量: {result[0]}条")
            safe_print(f"  日期范围: {result[1]} 到 {result[2]}")
        else:
            safe_print("  无数据")
        
        # 检查inventory域数据
        safe_print("\n[3] inventory域数据:")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as cnt,
                MIN(metric_date) as min_date,
                MAX(metric_date) as max_date
            FROM fact_product_metrics
            WHERE data_domain = 'inventory'
        """)).fetchone()
        
        if result and result[0] > 0:
            safe_print(f"  数量: {result[0]}条")
            safe_print(f"  日期范围: {result[1]} 到 {result[2]}")
        else:
            safe_print("  无数据")
        
        # 检查物化视图数据
        safe_print("\n[4] 物化视图数据:")
        try:
            result = db.execute(text("SELECT COUNT(*) FROM mv_product_management")).scalar()
            safe_print(f"  mv_product_management: {result}条")
        except Exception as e:
            safe_print(f"  mv_product_management: 不存在或错误 - {e}")
        
        safe_print("\n" + "="*70)
        
    finally:
        db.close()

if __name__ == "__main__":
    check_data()

