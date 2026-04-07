#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证所有Schema中的表都能有效迁移

检查public、a_class、b_class、c_class、core schema中的表是否都在迁移文件中。
特别关注A、B、C、core schema中的表。
"""

import sys
from pathlib import Path
from sqlalchemy import inspect, text

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from scripts.audit_all_tables import get_schema_tables, get_migration_tables


def safe_print(text_str, end="\n"):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, end=end, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, end=end, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, end=end, flush=True)


def get_all_tables_by_schema():
    """获取所有schema中的表（按schema分类）"""
    inspector = inspect(engine)
    schemas_to_check = ['public', 'a_class', 'b_class', 'c_class', 'core']
    
    all_tables_by_schema = {}
    
    conn = engine.connect()
    try:
        for schema in schemas_to_check:
            try:
                result = conn.execute(
                    text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}' ORDER BY table_name")
                )
                tables = [row[0] for row in result]
                all_tables_by_schema[schema] = set(tables)
            except Exception as e:
                safe_print(f"[WARNING] 无法查询 {schema} schema: {e}")
                all_tables_by_schema[schema] = set()
    finally:
        conn.close()
    
    return all_tables_by_schema


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("验证所有Schema中的表都能有效迁移")
    safe_print("=" * 80)
    safe_print("")
    
    # 1. 获取数据库中所有表（按schema分类）
    safe_print("[1] 查询数据库中所有表（按schema分类）...")
    db_tables_by_schema = get_all_tables_by_schema()
    
    total_db_tables = sum(len(tables) for tables in db_tables_by_schema.values())
    safe_print(f"  数据库中总计: {total_db_tables} 张表")
    safe_print("")
    
    for schema, tables in db_tables_by_schema.items():
        if tables:
            safe_print(f"  {schema}: {len(tables)} 张表")
            # 显示前10张表
            tables_list = sorted(list(tables))[:10]
            safe_print(f"    示例: {', '.join(tables_list)}{'...' if len(tables) > 10 else ''}")
    safe_print("")
    
    # 2. 获取schema.py中定义的表
    safe_print("[2] 分析schema.py中定义的表...")
    schema_tables = get_schema_tables()
    safe_print(f"  schema.py中定义: {len(schema_tables)} 张表")
    safe_print("")
    
    # 3. 获取迁移文件中记录的表
    safe_print("[3] 分析迁移文件中记录的表...")
    migration_tables_dict = get_migration_tables()
    all_migration_tables = set()
    for tables in migration_tables_dict.values():
        all_migration_tables.update(tables)
    safe_print(f"  迁移文件中记录: {len(all_migration_tables)} 张表（共 {len(migration_tables_dict)} 个迁移文件）")
    safe_print("")
    
    # 4. 检查各schema中的表
    safe_print("[4] 检查各Schema中的表...")
    safe_print("")
    
    critical_schemas = ['a_class', 'b_class', 'c_class', 'core', 'public']
    
    for schema in critical_schemas:
        db_tables = db_tables_by_schema.get(schema, set())
        if not db_tables:
            safe_print(f"  {schema}: 无表（可能不存在）")
            continue
        
        # 检查这些表是否在schema.py中定义
        in_schema_py = db_tables & schema_tables
        not_in_schema_py = db_tables - schema_tables
        
        # 检查这些表是否在迁移文件中
        in_migrations = db_tables & all_migration_tables
        not_in_migrations = db_tables - all_migration_tables
        
        safe_print(f"  {schema} ({len(db_tables)} 张表):")
        safe_print(f"    - 在schema.py中定义: {len(in_schema_py)} 张")
        safe_print(f"    - 不在schema.py中定义: {len(not_in_schema_py)} 张", end="")
        if not_in_schema_py:
            safe_print(f" ({', '.join(sorted(list(not_in_schema_py))[:5])}{'...' if len(not_in_schema_py) > 5 else ''})")
        else:
            safe_print("")
        safe_print(f"    - 在迁移文件中记录: {len(in_migrations)} 张")
        safe_print(f"    - 不在迁移文件中记录: {len(not_in_migrations)} 张", end="")
        if not_in_migrations:
            safe_print(f" ({', '.join(sorted(list(not_in_migrations))[:5])}{'...' if len(not_in_migrations) > 5 else ''})")
        else:
            safe_print("")
        
        # 如果不在迁移文件中，但使用Base.metadata.create_all()应该能创建
        if not_in_migrations and schema in ['a_class', 'b_class', 'c_class', 'core', 'public']:
            if in_schema_py:
                safe_print(f"    [NOTE] 这些表在schema.py中定义，Base.metadata.create_all()应该能创建")
            else:
                safe_print(f"    [WARNING] 这些表不在schema.py中定义，可能无法通过迁移创建")
        safe_print("")
    
    # 5. 总结
    safe_print("=" * 80)
    safe_print("总结")
    safe_print("=" * 80)
    safe_print("")
    
    # 检查public schema中的表
    public_tables = db_tables_by_schema.get('public', set())
    public_in_schema = public_tables & schema_tables
    public_in_migrations = public_tables & all_migration_tables
    
    safe_print(f"Public Schema:")
    safe_print(f"  - 总表数: {len(public_tables)}")
    safe_print(f"  - 在schema.py中定义: {len(public_in_schema)}")
    safe_print(f"  - 在迁移文件中记录: {len(public_in_migrations)}")
    safe_print(f"  - 缺失迁移记录: {len(public_tables - all_migration_tables)}")
    safe_print("")
    
    # 检查A、B、C、core schema
    other_schemas = ['a_class', 'b_class', 'c_class', 'core']
    for schema in other_schemas:
        schema_tables = db_tables_by_schema.get(schema, set())
        if schema_tables:
            schema_in_schema_py = schema_tables & schema_tables
            schema_in_migrations = schema_tables & all_migration_tables
            safe_print(f"{schema.upper()} Schema:")
            safe_print(f"  - 总表数: {len(schema_tables)}")
            safe_print(f"  - 在schema.py中定义: {len(schema_in_schema_py)}")
            safe_print(f"  - 在迁移文件中记录: {len(schema_in_migrations)}")
            safe_print(f"  - 缺失迁移记录: {len(schema_tables - all_migration_tables)}")
            safe_print("")
    
    # 最终结论
    all_db_tables_flat = set()
    for tables in db_tables_by_schema.values():
        all_db_tables_flat.update(tables)
    
    # 排除系统表
    system_tables = {'alembic_version', 'apscheduler_jobs'}
    all_db_tables_flat -= system_tables
    
    missing_in_migrations = all_db_tables_flat - all_migration_tables
    missing_in_schema_py = all_db_tables_flat - schema_tables
    
    safe_print("最终结论:")
    safe_print(f"  - 数据库中总表数: {len(all_db_tables_flat)} 张（排除系统表）")
    safe_print(f"  - 在schema.py中定义: {len(all_db_tables_flat & schema_tables)} 张")
    safe_print(f"  - 在迁移文件中记录: {len(all_db_tables_flat & all_migration_tables)} 张")
    safe_print(f"  - 缺失迁移记录: {len(missing_in_migrations)} 张")
    
    if missing_in_migrations:
        safe_print("")
        safe_print("缺失迁移记录的表（前20张）:")
        for table in sorted(list(missing_in_migrations))[:20]:
            # 找到这个表在哪个schema
            table_schema = None
            for schema, tables in db_tables_by_schema.items():
                if table in tables:
                    table_schema = schema
                    break
            in_schema_py = "✓" if table in schema_tables else "✗"
            safe_print(f"  {in_schema_py} {table_schema}.{table}")
    
    safe_print("")
    safe_print("注意:")
    safe_print("  - 使用 Base.metadata.create_all() 的迁移文件应该能创建所有在schema.py中定义的表")
    safe_print("  - 如果表在schema.py中定义但不在迁移文件中记录，Base.metadata.create_all()仍然能创建")
    safe_print("  - 如果表不在schema.py中定义，则无法通过迁移创建")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        safe_print(f"[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
