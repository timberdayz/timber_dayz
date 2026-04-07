#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查FactProductMetric表中inventory数据的实际情况
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_fact_inventory():
    safe_print("\n[INFO] 检查FactProductMetric表中inventory数据")
    
    db = SessionLocal()
    try:
        # 检查inventory数据总数
        total = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_product_metrics 
            WHERE data_domain = 'inventory'
        """)).scalar()
        
        safe_print(f"\n[INFO] inventory数据总数: {total}")
        
        # 检查source_catalog_id分布
        source_dist = db.execute(text("""
            SELECT 
                source_catalog_id,
                COUNT(*) as count
            FROM fact_product_metrics
            WHERE data_domain = 'inventory'
            GROUP BY source_catalog_id
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()
        
        safe_print(f"\n[INFO] source_catalog_id分布（前10）:")
        for source_id, count in source_dist:
            source_str = str(source_id) if source_id else "NULL"
            safe_print(f"  source_catalog_id={source_str}: {count} 条")
        
        # 检查创建时间范围
        time_range = db.execute(text("""
            SELECT 
                MIN(created_at) as min_time,
                MAX(created_at) as max_time,
                COUNT(*) as total
            FROM fact_product_metrics
            WHERE data_domain = 'inventory'
        """)).fetchone()
        
        safe_print(f"\n[INFO] 创建时间范围:")
        safe_print(f"  最早: {time_range[0]}")
        safe_print(f"  最晚: {time_range[1]}")
        safe_print(f"  总数: {time_range[2]}")
        
        # 检查file_id=1106的数据
        file_1106_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_product_metrics 
            WHERE source_catalog_id = 1106 AND data_domain = 'inventory'
        """)).scalar()
        
        safe_print(f"\n[INFO] file_id=1106的inventory数据: {file_1106_count} 条")
        
        # 检查是否有NULL的source_catalog_id
        null_count = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_product_metrics 
            WHERE source_catalog_id IS NULL AND data_domain = 'inventory'
        """)).scalar()
        
        safe_print(f"[INFO] source_catalog_id为NULL的inventory数据: {null_count} 条")
        
    finally:
        db.close()

if __name__ == "__main__":
    check_fact_inventory()

