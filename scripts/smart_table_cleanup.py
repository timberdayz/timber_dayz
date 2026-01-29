#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能数据库表清理脚本

根据 schema.py 定义和表名模式，智能判断哪些表应该保留，哪些应该删除
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

# 表应该所在的 schema 映射（根据 schema.py 定义）
TABLE_SCHEMA_MAP = {
    # core schema
    'platform_accounts': 'core',
    'accounts': 'core',  # platform_accounts 的别名？
    'data_files': 'core',
    'data_quarantine': 'core',
    'data_records': 'core',
    'dim_metric_formulas': 'core',
    'field_mapping_dictionary': 'core',
    'mapping_sessions': 'core',
    'staging_orders': 'core',
    'staging_product_metrics': 'core',
    
    # a_class schema
    'sales_targets_a': 'a_class',
    'sales_campaigns_a': 'a_class',
    'operating_costs': 'a_class',
    'employees': 'a_class',
    'employee_targets': 'a_class',
    'attendance_records': 'a_class',
    'performance_config_a': 'a_class',
    
    # b_class schema
    'entity_aliases': 'b_class',
    'staging_raw_data': 'b_class',
    
    # c_class schema
    'employee_performance': 'c_class',
    'employee_commissions': 'c_class',
    'shop_commissions': 'c_class',
    'performance_scores_c': 'c_class',
}

# 系统表（保留）
SYSTEM_TABLES = {'alembic_version'}

# 旧表映射（已废弃，应该删除 public 中的）
DEPRECATED_TABLES = {
    'sales_targets': 'a_class',  # 旧表，新的是 sales_targets_a
}

def get_table_schema(table_name):
    """根据表名判断应该所在的 schema"""
    # 检查映射表
    if table_name in TABLE_SCHEMA_MAP:
        return TABLE_SCHEMA_MAP[table_name]
    
    # 检查表名模式
    if table_name.endswith('_a'):
        return 'a_class'
    if table_name.endswith('_c'):
        return 'c_class'
    if table_name.startswith('fact_') and 'b_class' in str(Base.metadata.tables.get(table_name, {})):
        return 'b_class'
    
    # 默认在 public
    return 'public'

def get_all_tables_by_schema():
    """获取所有 schema 中的表"""
    inspector = inspect(engine)
    schemas = ['public', 'a_class', 'b_class', 'c_class', 'core', 'finance']
    
    tables_by_schema = {}
    for schema in schemas:
        try:
            tables = inspector.get_table_names(schema=schema)
            tables_by_schema[schema] = tables
        except:
            tables_by_schema[schema] = []
    
    return tables_by_schema

def get_table_row_count(schema, table_name):
    """获取表的行数"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'))
            return result.scalar() or 0
    except:
        return None

def main():
    safe_print("\n" + "="*80)
    safe_print("智能数据库表清理检查")
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
    
    # 获取所有表
    tables_by_schema = get_all_tables_by_schema()
    
    # 查找重复表
    safe_print("\n【查找重复表】")
    safe_print("-" * 80)
    
    table_locations = defaultdict(list)
    for schema, tables in tables_by_schema.items():
        for table in tables:
            table_locations[table].append(schema)
    
    duplicate_tables = {t: locs for t, locs in table_locations.items() if len(locs) > 1}
    
    cleanup_candidates = []
    
    for table_name, schemas in sorted(duplicate_tables.items()):
        if table_name in SYSTEM_TABLES:
            # 系统表，保留所有
            safe_print(f"  [SKIP] {table_name}: 系统表，保留所有位置")
            continue
        
        # 判断正确的 schema
        correct_schema = get_table_schema(table_name)
        
        # 检查 public 中是否有这个表
        if 'public' in schemas:
            public_count = get_table_row_count('public', table_name)
            correct_count = None
            if correct_schema in schemas:
                correct_count = get_table_row_count(correct_schema, table_name)
            
            # 如果正确的 schema 中有表，删除 public 中的
            if correct_schema != 'public' and correct_schema in schemas:
                safe_print(f"  [CLEANUP] {table_name}:")
                safe_print(f"    - public.{table_name}: {public_count or 0} 行（应删除）")
                safe_print(f"    - {correct_schema}.{table_name}: {correct_count or 0} 行（保留）")
                cleanup_candidates.append({
                    'table': table_name,
                    'schema': 'public',
                    'reason': f'重复表（正确位置在 {correct_schema}）',
                    'count': public_count or 0
                })
            elif correct_schema == 'public':
                # public 是正确的，删除其他 schema 中的
                for schema in schemas:
                    if schema != 'public':
                        count = get_table_row_count(schema, table_name)
                        safe_print(f"  [CLEANUP] {table_name}:")
                        safe_print(f"    - {schema}.{table_name}: {count or 0} 行（应删除）")
                        safe_print(f"    - public.{table_name}: {public_count or 0} 行（保留）")
                        cleanup_candidates.append({
                            'table': table_name,
                            'schema': schema,
                            'reason': f'重复表（正确位置在 public）',
                            'count': count or 0
                        })
            else:
                # 无法确定，需要人工确认
                safe_print(f"  [MANUAL] {table_name}: 需要人工确认")
                safe_print(f"    位置: {', '.join(schemas)}")
                safe_print(f"    预期位置: {correct_schema}")
    
    # 检查废弃表
    safe_print("\n【检查废弃表】")
    safe_print("-" * 80)
    
    public_tables = set(tables_by_schema.get('public', []))
    for table_name, correct_schema in DEPRECATED_TABLES.items():
        if table_name in public_tables:
            count = get_table_row_count('public', table_name)
            safe_print(f"  [CLEANUP] {table_name}: {count or 0} 行（已废弃，应删除）")
            cleanup_candidates.append({
                'table': table_name,
                'schema': 'public',
                'reason': f'废弃表（新表在 {correct_schema}）',
                'count': count or 0
            })
    
    # 执行清理
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
            safe_print(f"  原因: {item['reason']}")
            safe_print(f"  数据行数: {item['count']}")
            
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
    
    # 最终验证
    safe_print("\n" + "="*80)
    safe_print("【最终验证】")
    safe_print("="*80)
    
    tables_by_schema_after = get_all_tables_by_schema()
    total_before = sum(len(tables) for tables in tables_by_schema.values())
    total_after = sum(len(tables) for tables in tables_by_schema_after.values())
    
    safe_print(f"清理前: {total_before} 张表")
    safe_print(f"清理后: {total_after} 张表")
    safe_print(f"删除: {total_before - total_after} 张表")
    
    # 重新检查重复表
    table_locations_after = defaultdict(list)
    for schema, tables in tables_by_schema_after.items():
        for table in tables:
            table_locations_after[table].append(schema)
    
    duplicate_after = {t: locs for t, locs in table_locations_after.items() if len(locs) > 1}
    duplicate_after = {t: locs for t, locs in duplicate_after.items() if t not in SYSTEM_TABLES}
    
    if duplicate_after:
        safe_print(f"\n清理后仍有 {len(duplicate_after)} 张重复表（需要人工确认）:")
        for table, schemas in sorted(duplicate_after.items()):
            safe_print(f"  - {table}: {', '.join(schemas)}")
    else:
        safe_print("\n✓ 清理后无重复表")
    
    safe_print("\n检查完成！")

if __name__ == "__main__":
    main()
