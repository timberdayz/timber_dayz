#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查fact_order_items表结构
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine, SessionLocal
from sqlalchemy import inspect, text
from modules.core.db import FactOrderItem

def check_table_schema():
    """检查fact_order_items表结构"""
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        
        # 检查表是否存在
        tables = inspector.get_table_names()
        if 'fact_order_items' not in tables:
            print("[ERROR] fact_order_items表不存在！")
            return
        
        # 获取表的所有字段
        columns = inspector.get_columns('fact_order_items')
        column_names = [c['name'] for c in columns]
        
        print(f"[INFO] fact_order_items表字段 ({len(column_names)}个):")
        for col in columns:
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            print(f"  - {col['name']}: {col['type']} ({nullable})")
        
        # 检查是否有platform_code字段
        if 'platform_code' not in column_names:
            print("\n[ERROR] fact_order_items表缺少platform_code字段！")
            print("[INFO] 需要运行数据库迁移脚本添加此字段")
            
            # 检查FactOrderItem模型定义
            print("\n[INFO] FactOrderItem模型定义的字段:")
            from sqlalchemy.inspection import inspect as sa_inspect
            mapper = sa_inspect(FactOrderItem)
            for col in mapper.columns:
                print(f"  - {col.name}: {col.type} ({'NULL' if col.nullable else 'NOT NULL'})")
        else:
            print("\n[OK] fact_order_items表包含platform_code字段")
        
        # 检查索引
        indexes = inspector.get_indexes('fact_order_items')
        print(f"\n[INFO] fact_order_items表索引 ({len(indexes)}个):")
        for idx in indexes:
            print(f"  - {idx['name']}: {idx['column_names']}")
        
        # 检查主键
        pk_constraint = inspector.get_pk_constraint('fact_order_items')
        if pk_constraint:
            print(f"\n[INFO] fact_order_items表主键: {pk_constraint['constrained_columns']}")
        
    except Exception as e:
        print(f"[ERROR] 检查表结构失败: {e}", exc_info=True)
    finally:
        db.close()

if __name__ == '__main__':
    check_table_schema()

