#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的数据库表清理检查脚本

检查：
1. public schema 中的所有表
2. 对比 schema.py 中定义的表
3. 查找重复表（多个 schema 中存在）
4. 查找废弃表（不在 schema.py 中定义）
5. 生成清理建议并执行清理
"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import engine
from backend.utils.config import get_settings
from modules.core.db import Base

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)

def get_all_tables_by_schema():
    """获取所有 schema 中的表"""
    inspector = inspect(engine)
    schemas = ['public', 'a_class', 'b_class', 'c_class', 'core', 'finance']
    
    tables_by_schema = {}
    for schema in schemas:
        try:
            tables = inspector.get_table_names(schema=schema)
            tables_by_schema[schema] = tables
        except Exception as e:
            # schema 可能不存在
            tables_by_schema[schema] = []
    
    return tables_by_schema

def get_schema_py_tables():
    """获取 schema.py 中定义的所有表名"""
    return set(Base.metadata.tables.keys())

def get_table_row_count(schema, table_name):
    """获取表的行数"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'))
            return result.scalar() or 0
    except Exception as e:
        return None

def check_system_tables():
    """系统表列表（不应该删除）"""
    return {
        'alembic_version',  # Alembic 版本表
        'apscheduler_jobs',  # APScheduler 任务表
    }

def check_deprecated_tables():
    """已知废弃表列表"""
    deprecated = {
        'fact_orders',  # v4.6.0 后废弃，已迁移到 b_class
        'fact_order_items',  # v4.6.0 后废弃，已迁移到 b_class
    }
    return deprecated

def main():
    safe_print("\n" + "="*80)
    safe_print("完整的数据库表清理检查")
    safe_print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print("="*80)
    
    # 显示数据库连接信息
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if '@' in db_url:
        parts = db_url.split('@')
        if len(parts) == 2:
            host_part = parts[1].split('/')
            if len(host_part) >= 2:
                host_port = host_part[0]
                db_name = host_part[1].split('?')[0]
                safe_print(f"\n[INFO] 数据库: {db_name} @ {host_port}")
    
    # 1. 获取所有表
    safe_print("\n【1. 扫描所有 schema 中的表】")
    safe_print("-" * 80)
    
    tables_by_schema = get_all_tables_by_schema()
    total_tables = sum(len(tables) for tables in tables_by_schema.values())
    safe_print(f"总计发现 {total_tables} 张表:")
    
    for schema, tables in tables_by_schema.items():
        if tables:
            safe_print(f"  {schema}: {len(tables)} 张表")
    
    # 2. 获取 schema.py 中定义的表
    safe_print("\n【2. 对比 schema.py 中定义的表】")
    safe_print("-" * 80)
    
    schema_py_tables = get_schema_py_tables()
    safe_print(f"schema.py 中定义的表: {len(schema_py_tables)} 张")
    
    # 3. 查找重复表（多个 schema 中存在）
    safe_print("\n【3. 查找重复表（多个 schema 中存在）】")
    safe_print("-" * 80)
    
    table_locations = defaultdict(list)
    for schema, tables in tables_by_schema.items():
        for table in tables:
            table_locations[table].append(schema)
    
    duplicate_tables = {t: locs for t, locs in table_locations.items() if len(locs) > 1}
    
    if duplicate_tables:
        safe_print(f"发现 {len(duplicate_tables)} 张重复表:")
        for table, schemas in sorted(duplicate_tables.items()):
            safe_print(f"  {table}: {', '.join(schemas)}")
    else:
        safe_print("✓ 未发现重复表")
    
    # 4. 查找 public schema 中的废弃表
    safe_print("\n【4. 检查 public schema 中的表】")
    safe_print("-" * 80)
    
    public_tables = set(tables_by_schema.get('public', []))
    system_tables = check_system_tables()
    deprecated_tables = check_deprecated_tables()
    
    # 分类 public 中的表
    defined_in_schema_py = []
    not_in_schema_py = []
    system = []
    deprecated = []
    
    for table in public_tables:
        # 移除 schema 前缀（如果有）
        table_name = table.split('.')[-1]
        
        if table_name in system_tables:
            system.append(table_name)
        elif table_name in deprecated_tables:
            deprecated.append(table_name)
        elif table_name in schema_py_tables:
            defined_in_schema_py.append(table_name)
        else:
            not_in_schema_py.append(table_name)
    
    safe_print(f"\npublic schema 表分类:")
    safe_print(f"  ✓ schema.py 中定义: {len(defined_in_schema_py)} 张")
    safe_print(f"  ⚠ 系统表（保留）: {len(system)} 张 - {', '.join(sorted(system))}")
    safe_print(f"  ⚠ 已知废弃表: {len(deprecated)} 张 - {', '.join(sorted(deprecated))}")
    safe_print(f"  ⚠ 不在 schema.py 中: {len(not_in_schema_py)} 张")
    
    if not_in_schema_py:
        safe_print(f"\n不在 schema.py 中的表列表:")
        for table in sorted(not_in_schema_py):
            # 检查是否有数据
            count = get_table_row_count('public', table)
            if count is not None:
                safe_print(f"  - {table} ({count} 行)")
            else:
                safe_print(f"  - {table} (无法查询)")
    
    # 5. 检查其他 schema 中是否有应该在 public 的表
    safe_print("\n【5. 检查其他 schema 中的表】")
    safe_print("-" * 80)
    
    other_schema_issues = []
    for schema in ['a_class', 'b_class', 'c_class', 'core', 'finance']:
        tables = tables_by_schema.get(schema, [])
        if tables:
            safe_print(f"\n{schema} schema: {len(tables)} 张表")
            # 检查是否有表应该在 public 但在这里
            for table in tables:
                if table in schema_py_tables:
                    # 检查这个表是否应该在当前 schema
                    # 这里需要根据实际 schema 定义来判断
                    pass
    
    # 6. 生成清理建议
    safe_print("\n" + "="*80)
    safe_print("【清理建议】")
    safe_print("="*80)
    
    cleanup_candidates = []
    
    # 废弃表
    for table in deprecated:
        if table in public_tables:
            count = get_table_row_count('public', table)
            cleanup_candidates.append({
                'table': table,
                'schema': 'public',
                'reason': '已知废弃表（v4.6.0后已迁移到b_class）',
                'count': count or 0,
                'action': 'delete'
            })
    
    # 重复表（保留正确位置的，删除 public 中的）
    for table, schemas in duplicate_tables.items():
        if 'public' in schemas:
            # 检查哪个 schema 是正确的
            if 'a_class' in schemas and table.startswith(('sales_targets', 'sales_targets_a', 'sales_campaigns_a', 'operating_costs', 'employees', 'employee_targets', 'attendance_records', 'performance_config_a')):
                cleanup_candidates.append({
                    'table': table,
                    'schema': 'public',
                    'reason': f'重复表（已在 a_class schema 中存在）',
                    'count': get_table_row_count('public', table) or 0,
                    'action': 'delete'
                })
            elif 'c_class' in schemas and table.startswith(('employee_performance', 'employee_commissions', 'shop_commissions', 'performance_scores', 'shop_health_scores', 'shop_alerts')):
                cleanup_candidates.append({
                    'table': table,
                    'schema': 'public',
                    'reason': f'重复表（已在 c_class schema 中存在）',
                    'count': get_table_row_count('public', table) or 0,
                    'action': 'delete'
                })
    
    # 不在 schema.py 中的表（需要人工确认）
    unknown_tables = []
    for table in not_in_schema_py:
        if table not in system_tables and table not in deprecated_tables:
            count = get_table_row_count('public', table)
            unknown_tables.append({
                'table': table,
                'count': count or 0,
                'reason': '不在 schema.py 中定义'
            })
    
    if cleanup_candidates:
        safe_print(f"\n可以安全删除的表 ({len(cleanup_candidates)} 张):")
        for item in cleanup_candidates:
            safe_print(f"  - {item['schema']}.{item['table']} ({item['count']} 行) - {item['reason']}")
    
    if unknown_tables:
        safe_print(f"\n需要人工确认的表 ({len(unknown_tables)} 张):")
        for item in unknown_tables:
            safe_print(f"  - public.{item['table']} ({item['count']} 行) - {item['reason']}")
        safe_print("\n  注意: 这些表不在 schema.py 中，请确认是否仍在使用")
    
    # 7. 执行清理
    if cleanup_candidates:
        safe_print("\n" + "="*80)
        safe_print("【执行清理】")
        safe_print("="*80)
        
        deleted_count = 0
        failed_count = 0
        
        for item in cleanup_candidates:
            table = item['table']
            schema = item['schema']
            
            safe_print(f"\n删除 {schema}.{table}...")
            try:
                with engine.connect() as conn:
                    # 先删除外键约束
                    conn.execute(text(f"""
                        DO $$ 
                        DECLARE
                            r RECORD;
                        BEGIN
                            FOR r IN (
                                SELECT constraint_name, table_name
                                FROM information_schema.table_constraints
                                WHERE constraint_type = 'FOREIGN KEY'
                                AND table_name = '{table}'
                                AND table_schema = '{schema}'
                            ) LOOP
                                EXECUTE 'ALTER TABLE "{schema}".' || quote_ident(r.table_name) || 
                                        ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.constraint_name);
                            END LOOP;
                        END $$;
                    """))
                    
                    # 删除表
                    conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE'))
                    conn.commit()
                    safe_print(f"  [OK] {schema}.{table} 已删除")
                    deleted_count += 1
            except Exception as e:
                safe_print(f"  [ERROR] 删除失败: {e}")
                failed_count += 1
        
        safe_print(f"\n清理完成: 成功 {deleted_count} 张，失败 {failed_count} 张")
    else:
        safe_print("\n没有需要清理的表")
    
    # 8. 最终验证
    safe_print("\n" + "="*80)
    safe_print("【最终验证】")
    safe_print("="*80)
    
    # 重新扫描
    tables_by_schema_after = get_all_tables_by_schema()
    total_tables_after = sum(len(tables) for tables in tables_by_schema_after.values())
    
    safe_print(f"清理前: {total_tables} 张表")
    safe_print(f"清理后: {total_tables_after} 张表")
    safe_print(f"删除: {total_tables - total_tables_after} 张表")
    
    safe_print("\n检查完成！")

if __name__ == "__main__":
    main()
