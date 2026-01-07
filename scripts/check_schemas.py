#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中的schema分布
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def check_schemas():
    """检查数据库中的schema分布"""
    db = next(get_db())
    
    try:
        # 检查所有schema
        result = db.execute(text("""
            SELECT schemaname, COUNT(*) as table_count
            FROM pg_tables 
            WHERE schemaname IN ('b_class', 'a_class', 'c_class', 'core', 'public', 'finance')
            GROUP BY schemaname
            ORDER BY schemaname
        """))
        
        print("=" * 70)
        print("数据库Schema分布")
        print("=" * 70)
        
        schemas_found = []
        for row in result:
            schema_name, table_count = row
            schemas_found.append(schema_name)
            print(f"  {schema_name}: {table_count}表")
        
        if not schemas_found:
            print("\n[WARNING] 没有找到任何表！")
        else:
            print(f"\n总共找到 {len(schemas_found)} 个schema")
        
        # 检查b_class schema中的表
        print("\n" + "=" * 70)
        print("b_class schema中的表（前10个）")
        print("=" * 70)
        result = db.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'b_class'
            LIMIT 10
        """))
        b_class_tables = [row[0] for row in result]
        if b_class_tables:
            for table in b_class_tables:
                print(f"  {table}")
        else:
            print("  [WARNING] b_class schema中没有表")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_schemas()

