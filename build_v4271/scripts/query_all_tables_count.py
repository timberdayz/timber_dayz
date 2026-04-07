#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询 Docker 容器中 PostgreSQL 数据库的所有表数量（按 schema 分类）

用于确认实际数据库中的表数量，而不是只统计 public schema 的表
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from backend.models.database import engine
from modules.core.db import Base


def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def main():
    safe_print("=" * 80)
    safe_print("Docker 容器 PostgreSQL 表数量统计（完整）")
    safe_print("=" * 80)
    
    inspector = inspect(engine)
    
    # 方法 1: 使用 SQLAlchemy inspector（可能只统计 public schema）
    safe_print("\n[方法 1] SQLAlchemy inspector.get_table_names()（默认）")
    default_tables = inspector.get_table_names()
    safe_print(f"  返回表数量: {len(default_tables)} 张")
    
    # 方法 2: 获取所有 schema 的表（正确方法）
    safe_print("\n[方法 2] 按 Schema 分类统计（正确方法）")
    schemas = inspector.get_schema_names()
    user_schemas = [s for s in schemas if s not in ['pg_catalog', 'information_schema', 'pg_toast']]
    
    total_by_schema = 0
    for schema in sorted(user_schemas):
        try:
            tables = inspector.get_table_names(schema=schema)
            count = len(tables)
            if count > 0:
                safe_print(f"  {schema}: {count} 张表")
                total_by_schema += count
        except Exception as e:
            safe_print(f"  {schema}: 查询失败 ({e})")
    
    safe_print(f"\n  按 schema 分类总计: {total_by_schema} 张表")
    
    # 方法 3: 使用 SQL 直接查询（最准确）
    safe_print("\n[方法 3] SQL 直接查询（最准确）")
    with engine.connect() as conn:
        # 按 schema 分类
        query = text("""
            SELECT 
                table_schema,
                COUNT(*) as table_count
            FROM information_schema.tables 
            WHERE table_type = 'BASE TABLE'
                AND table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            GROUP BY table_schema
            ORDER BY table_schema
        """)
        result = conn.execute(query)
        
        total_by_sql = 0
        for row in result:
            schema_name = row[0]
            count = row[1]
            safe_print(f"  {schema_name}: {count} 张表")
            total_by_sql += count
        
        safe_print(f"\n  SQL 查询总计: {total_by_sql} 张表")
        
        # 总表数量（不分 schema）
        query_total = text("""
            SELECT COUNT(*) as total_tables
            FROM information_schema.tables 
            WHERE table_type = 'BASE TABLE'
                AND table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        """)
        total_result = conn.execute(query_total).scalar()
        safe_print(f"\n  数据库实际总表数: {total_result} 张表")
    
    # 方法 4: 统计 schema.py 中定义的表
    safe_print("\n[方法 4] schema.py 中定义的表（预期）")
    expected_tables = set(Base.metadata.tables.keys())
    safe_print(f"  schema.py 中定义的表数量: {len(expected_tables)} 张")
    
    # 对比
    safe_print("\n" + "=" * 80)
    safe_print("对比总结")
    safe_print("=" * 80)
    safe_print(f"  SQLAlchemy inspector（默认）: {len(default_tables)} 张表")
    safe_print(f"  SQLAlchemy inspector（按 schema）: {total_by_schema} 张表")
    safe_print(f"  SQL 直接查询: {total_by_sql} 张表")
    safe_print(f"  schema.py 定义（预期）: {len(expected_tables)} 张表")
    
    if len(default_tables) != total_by_sql:
        safe_print(f"\n  [WARNING] SQLAlchemy inspector（默认）只统计了 {len(default_tables)} 张表")
        safe_print(f"            SQL 查询显示实际有 {total_by_sql} 张表")
        safe_print(f"            差异: {total_by_sql - len(default_tables)} 张表（可能在其他 schema 中）")
    
    safe_print("\n" + "=" * 80)
    safe_print("结论")
    safe_print("=" * 80)
    safe_print(f"Docker 容器中 PostgreSQL 数据库实际有 {total_by_sql} 张表（所有 schema）")
    safe_print(f"verify_schema_completeness() 函数只统计了 {len(default_tables)} 张表（可能只统计了 public schema）")
    safe_print("=" * 80)


if __name__ == "__main__":
    main()
