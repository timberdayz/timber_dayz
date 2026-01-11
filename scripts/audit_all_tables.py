#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计所有数据库表，确认每张表的来源

分析：
1. schema.py 中定义的表
2. 迁移文件中创建的表
3. 历史遗留表（不在 schema.py 中，也无迁移记录）
4. 系统表（alembic_version 等）
"""

import sys
import re
from pathlib import Path
from collections import defaultdict
from typing import Set, Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from backend.models.database import engine
from modules.core.db import Base


def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def get_schema_tables() -> Set[str]:
    """获取 schema.py 中定义的所有表"""
    tables = set()
    schema_file = Path("modules/core/db/schema.py")
    content = schema_file.read_text(encoding='utf-8')
    
    for match in re.finditer(r'__tablename__\s*=\s*["\'](\w+)["\']', content):
        tables.add(match.group(1))
    
    return tables


def get_migration_tables() -> Dict[str, Set[str]]:
    """获取迁移文件中创建的所有表"""
    migration_tables = defaultdict(set)
    migrations_dir = Path("migrations/versions")
    
    if not migrations_dir.exists():
        return {}
    
    for migration_file in migrations_dir.glob("*.py"):
        if migration_file.name == "__init__.py":
            continue
        
        content = migration_file.read_text(encoding='utf-8')
        revision_match = re.search(r"revision\s*=\s*['\"](\w+)['\"]", content)
        if not revision_match:
            continue
        
        revision = revision_match.group(1)
        
        # 查找 create_table 调用
        create_table_pattern = r"op\.create_table\(['\"](\w+)['\"]"
        for match in re.finditer(create_table_pattern, content):
            table_name = match.group(1)
            migration_tables[revision].add(table_name)
        
        # 查找 CREATE TABLE 语句（SQL格式）
        create_table_sql_pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[\w.]+\.)?['\"]?(\w+)['\"]?"
        for match in re.finditer(create_table_sql_pattern, content, re.IGNORECASE):
            table_name = match.group(1)
            # 排除系统关键字
            if table_name.lower() not in ['select', 'from', 'where', 'if', 'not', 'exists']:
                migration_tables[revision].add(table_name)
    
    return dict(migration_tables)


def get_all_database_tables() -> Dict[str, List[str]]:
    """获取数据库中所有实际存在的表（按 schema 分类）"""
    inspector = inspect(engine)
    schemas = inspector.get_schema_names()
    user_schemas = [s for s in schemas if s not in ['pg_catalog', 'information_schema', 'pg_toast']]
    
    tables_by_schema = {}
    for schema in sorted(user_schemas):
        try:
            tables = inspector.get_table_names(schema=schema)
            if tables:
                tables_by_schema[schema] = sorted(tables)
        except Exception as e:
            safe_print(f"[WARNING] 无法获取 schema {schema} 的表: {e}")
    
    return tables_by_schema


def get_system_tables() -> Set[str]:
    """获取系统表列表"""
    return {
        'alembic_version',
        'apscheduler_jobs',  # APScheduler 系统表
    }


def main():
    safe_print("=" * 80)
    safe_print("数据库表审计报告")
    safe_print("=" * 80)
    
    # 1. 获取 schema.py 中定义的表
    safe_print("\n[1] 分析 schema.py 中定义的表...")
    schema_tables = get_schema_tables()
    safe_print(f"  schema.py 中定义了 {len(schema_tables)} 张表")
    
    # 2. 获取迁移文件中创建的表
    safe_print("\n[2] 分析迁移文件中创建的表...")
    migration_tables_dict = get_migration_tables()
    all_migration_tables = set()
    for tables in migration_tables_dict.values():
        all_migration_tables.update(tables)
    safe_print(f"  迁移文件中创建了 {len(all_migration_tables)} 张表（共 {len(migration_tables_dict)} 个迁移文件）")
    
    # 3. 获取数据库中实际存在的表
    safe_print("\n[3] 分析数据库中实际存在的表...")
    db_tables_by_schema = get_all_database_tables()
    all_db_tables = set()
    for tables in db_tables_by_schema.values():
        all_db_tables.update(tables)
    
    total_db_tables = len(all_db_tables)
    safe_print(f"  数据库中实际有 {total_db_tables} 张表（所有 schema）")
    for schema, tables in db_tables_by_schema.items():
        safe_print(f"    {schema}: {len(tables)} 张表")
    
    # 4. 获取系统表
    system_tables = get_system_tables()
    
    # 5. 分类分析
    safe_print("\n" + "=" * 80)
    safe_print("分类分析")
    safe_print("=" * 80)
    
    # 5.1 schema.py 中定义但数据库中不存在的表
    missing_in_db = schema_tables - all_db_tables
    if missing_in_db:
        safe_print(f"\n[缺失] schema.py 中定义但数据库中不存在的表 ({len(missing_in_db)} 张):")
        for table in sorted(missing_in_db):
            safe_print(f"  - {table}")
    
    # 5.2 数据库中存在但 schema.py 中未定义的表
    extra_in_db = all_db_tables - schema_tables - system_tables
    if extra_in_db:
        safe_print(f"\n[额外] 数据库中存在但 schema.py 中未定义的表 ({len(extra_in_db)} 张):")
        for table in sorted(extra_in_db):
            safe_print(f"  - {table}")
    
    # 5.3 schema.py 中定义但迁移文件中未创建的表
    missing_in_migration = schema_tables - all_migration_tables - system_tables
    if missing_in_migration:
        safe_print(f"\n[未迁移] schema.py 中定义但迁移文件中未创建的表 ({len(missing_in_migration)} 张):")
        for table in sorted(missing_in_migration):
            safe_print(f"  - {table}")
    
    # 5.4 历史遗留表（不在 schema.py 中，也不在迁移文件中）
    legacy_tables = extra_in_db - all_migration_tables
    if legacy_tables:
        safe_print(f"\n[历史遗留] 不在 schema.py 中，也不在迁移文件中的表 ({len(legacy_tables)} 张):")
        # 按 schema 分类显示
        legacy_by_schema = defaultdict(list)
        for schema, tables in db_tables_by_schema.items():
            for table in tables:
                if table in legacy_tables:
                    legacy_by_schema[schema].append(table)
        
        for schema, tables in sorted(legacy_by_schema.items()):
            safe_print(f"\n  [{schema}] schema ({len(tables)} 张):")
            for table in sorted(tables):
                safe_print(f"    - {table}")
    
    # 5.5 系统表
    system_in_db = system_tables & all_db_tables
    if system_in_db:
        safe_print(f"\n[系统表] 系统表 ({len(system_in_db)} 张):")
        for table in sorted(system_in_db):
            safe_print(f"  - {table}")
    
    # 6. 统计总结
    safe_print("\n" + "=" * 80)
    safe_print("统计总结")
    safe_print("=" * 80)
    safe_print(f"  schema.py 定义的表: {len(schema_tables)} 张")
    safe_print(f"  迁移文件中创建的表: {len(all_migration_tables)} 张")
    safe_print(f"  数据库中实际存在的表: {total_db_tables} 张")
    safe_print(f"  系统表: {len(system_in_db)} 张")
    safe_print(f"  缺失的表（schema.py 中但数据库中不存在）: {len(missing_in_db)} 张")
    safe_print(f"  额外的表（数据库中但 schema.py 中未定义）: {len(extra_in_db)} 张")
    safe_print(f"  未迁移的表（schema.py 中但迁移文件中未创建）: {len(missing_in_migration)} 张")
    safe_print(f"  历史遗留表（不在 schema.py 中，也不在迁移文件中）: {len(legacy_tables)} 张")
    
    # 7. 按 schema 详细列表（输出到文件）
    output_file = project_root / "temp" / "table_audit_report.txt"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("数据库表审计详细报告\n")
        f.write("=" * 80 + "\n\n")
        
        for schema, tables in sorted(db_tables_by_schema.items()):
            f.write(f"\n[{schema}] schema ({len(tables)} 张表):\n")
            f.write("-" * 80 + "\n")
            
            for table in tables:
                status = []
                if table in schema_tables:
                    status.append("schema.py")
                if table in all_migration_tables:
                    status.append("迁移")
                if table in system_tables:
                    status.append("系统表")
                if table in legacy_tables:
                    status.append("历史遗留")
                
                status_str = ", ".join(status) if status else "未知"
                f.write(f"  {table:50s} [{status_str}]\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("分类汇总\n")
        f.write("=" * 80 + "\n\n")
        
        if missing_in_db:
            f.write(f"缺失的表 ({len(missing_in_db)} 张):\n")
            for table in sorted(missing_in_db):
                f.write(f"  - {table}\n")
            f.write("\n")
        
        if missing_in_migration:
            f.write(f"未迁移的表 ({len(missing_in_migration)} 张):\n")
            for table in sorted(missing_in_migration):
                f.write(f"  - {table}\n")
            f.write("\n")
        
        if legacy_tables:
            f.write(f"历史遗留表 ({len(legacy_tables)} 张):\n")
            for table in sorted(legacy_tables):
                f.write(f"  - {table}\n")
            f.write("\n")
    
    safe_print(f"\n[INFO] 详细报告已保存到: {output_file}")
    safe_print("=" * 80)


if __name__ == "__main__":
    main()
