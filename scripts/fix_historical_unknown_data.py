#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复历史数据：将unknown平台的数据更新为miaoshou
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text

def main():
    print("=== 修复历史数据：unknown -> miaoshou ===\n")

    with engine.connect() as conn:
        # 1. 检查需要修复的数据
        print("--- Step 1: 检查需要修复的数据 ---")
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM fact_product_metrics
            WHERE platform_code = 'unknown'
              AND warehouse LIKE '%新加坡%'
              AND total_stock IS NOT NULL
              AND available_stock IS NOT NULL;
        """))
        count = result.fetchone()[0]
        print(f"  需要修复的数据: {count}条")
        
        if count == 0:
            print("  没有需要修复的数据！")
            return
        
        # 2. 预览修复前的数据
        print("\n--- Step 2: 预览修复前的数据 ---")
        result = conn.execute(text("""
            SELECT 
                id, platform_code, platform_sku, product_name,
                warehouse, total_stock, available_stock, price
            FROM fact_product_metrics
            WHERE platform_code = 'unknown'
              AND warehouse LIKE '%新加坡%'
              AND total_stock IS NOT NULL
              AND available_stock IS NOT NULL
            LIMIT 5;
        """))
        
        print("  修复前数据样本:")
        for row in result.fetchall():
            print(f"    ID: {row[0]}, Platform: {row[1]}, SKU: {row[2]}")
            print(f"      Name: {row[3]}")
            print(f"      Warehouse: {row[4]}, Stock: {row[5]}/{row[6]}, Price: {row[7]}")
        
        # 3. 执行修复
        print("\n--- Step 3: 执行修复 ---")
        result = conn.execute(text("""
            UPDATE fact_product_metrics
            SET platform_code = 'miaoshou'
            WHERE platform_code = 'unknown'
              AND warehouse LIKE '%新加坡%'
              AND total_stock IS NOT NULL
              AND available_stock IS NOT NULL;
        """))
        conn.commit()
        
        print(f"  修复完成: {result.rowcount}条数据已更新")
        
        # 4. 验证修复结果
        print("\n--- Step 4: 验证修复结果 ---")
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM fact_product_metrics
            WHERE platform_code = 'miaoshou';
        """))
        miaoshou_count = result.fetchone()[0]
        print(f"  Miaoshou平台数据: {miaoshou_count}条")
        
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM fact_product_metrics
            WHERE platform_code = 'unknown'
              AND warehouse LIKE '%新加坡%'
              AND total_stock IS NOT NULL;
        """))
        remaining_count = result.fetchone()[0]
        print(f"  剩余unknown平台数据（含新加坡）: {remaining_count}条")

if __name__ == "__main__":
    main()

