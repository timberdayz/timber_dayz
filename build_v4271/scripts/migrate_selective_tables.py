#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
选择性表迁移工具

支持指定表列表迁移、增量迁移、数据验证

用法:
    python scripts/migrate_selective_tables.py --source <source_db_url> --target <target_db_url> --tables "table1,table2"
    python scripts/migrate_selective_tables.py --source <source_db_url> --target <target_db_url> --incremental
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Set
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import Engine
    import psycopg2
except ImportError as e:
    print(f"[ERROR] Failed to import required modules: {e}")
    print("[INFO] Please install: pip install sqlalchemy psycopg2-binary")
    sys.exit(1)


def safe_print(text: str):
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


def get_table_names(engine: Engine) -> Set[str]:
    """获取数据库中的所有表名"""
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def get_table_row_count(engine: Engine, table_name: str) -> int:
    """获取表的记录数"""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar() or 0


def migrate_table(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    incremental: bool = False,
    where_clause: Optional[str] = None
) -> bool:
    """迁移单个表的数据"""
    try:
        # 检查表是否存在
        source_tables = get_table_names(source_engine)
        target_tables = get_table_names(target_engine)
        
        if table_name not in source_tables:
            safe_print(f"[WARN] Table {table_name} does not exist in source database")
            return False
        
        if table_name not in target_tables:
            safe_print(f"[WARN] Table {table_name} does not exist in target database")
            return False
        
        # 获取源表数据
        safe_print(f"[INFO] Exporting data from {table_name}...")
        
        with source_engine.connect() as source_conn:
            query = f"SELECT * FROM {table_name}"
            if where_clause:
                query += f" WHERE {where_clause}"
            elif incremental:
                # 增量迁移：只迁移最近的数据（假设有 created_at 或 updated_at 字段）
                query += " WHERE updated_at > (SELECT MAX(updated_at) FROM {table_name})"
            
            result = source_conn.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()
        
        if not rows:
            safe_print(f"[INFO] No data to migrate for {table_name}")
            return True
        
        safe_print(f"[INFO] Found {len(rows)} rows to migrate")
        
        # 导入数据到目标表
        safe_print(f"[INFO] Importing data to {table_name}...")
        
        with target_engine.connect() as target_conn:
            # 构建 INSERT 语句
            columns_str = ', '.join(columns)
            placeholders = ', '.join([':' + col for col in columns])
            insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            
            # 批量插入
            batch_size = 1000
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                data = [dict(zip(columns, row)) for row in batch]
                target_conn.execute(text(insert_sql), data)
                target_conn.commit()
                safe_print(f"[INFO] Inserted {min(i + batch_size, len(rows))}/{len(rows)} rows")
        
        safe_print(f"[OK] Table {table_name} migrated successfully")
        return True
        
    except Exception as e:
        safe_print(f"[ERROR] Failed to migrate table {table_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration(
    source_engine: Engine,
    target_engine: Engine,
    table_names: List[str]
) -> bool:
    """验证迁移结果"""
    safe_print("[INFO] Verifying migration...")
    
    all_verified = True
    for table_name in table_names:
        try:
            source_count = get_table_row_count(source_engine, table_name)
            target_count = get_table_row_count(target_engine, table_name)
            
            if source_count == target_count:
                safe_print(f"[OK] {table_name}: {source_count} rows (verified)")
            else:
                safe_print(f"[WARN] {table_name}: source={source_count}, target={target_count} (mismatch)")
                all_verified = False
        except Exception as e:
            safe_print(f"[ERROR] Failed to verify {table_name}: {e}")
            all_verified = False
    
    return all_verified


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Selective table migration tool")
    parser.add_argument("--source", required=True, help="Source database URL")
    parser.add_argument("--target", required=True, help="Target database URL")
    parser.add_argument("--tables", help="Comma-separated table list")
    parser.add_argument("--incremental", action="store_true", help="Incremental migration mode")
    parser.add_argument("--where", help="WHERE clause for filtering data")
    parser.add_argument("--verify", action="store_true", help="Verify migration after completion")
    parser.add_argument("--verify-only", action="store_true", help="Only verify, do not migrate")
    
    args = parser.parse_args()
    
    # 创建数据库连接
    try:
        source_engine = create_engine(args.source)
        target_engine = create_engine(args.target)
    except Exception as e:
        safe_print(f"[ERROR] Failed to create database connections: {e}")
        sys.exit(1)
    
    # 获取要迁移的表列表
    if args.tables:
        table_names = [t.strip() for t in args.tables.split(',')]
    else:
        # 如果没有指定表，迁移所有表
        source_tables = get_table_names(source_engine)
        target_tables = get_table_names(target_engine)
        table_names = sorted(list(source_tables & target_tables))
        safe_print(f"[INFO] No tables specified, migrating all common tables: {len(table_names)} tables")
    
    if not table_names:
        safe_print("[ERROR] No tables to migrate")
        sys.exit(1)
    
    safe_print(f"[INFO] Starting migration: {len(table_names)} tables")
    safe_print(f"[INFO] Mode: {'incremental' if args.incremental else 'full'}")
    
    # 仅验证模式
    if args.verify_only:
        if verify_migration(source_engine, target_engine, table_names):
            safe_print("[OK] Verification passed")
            sys.exit(0)
        else:
            safe_print("[ERROR] Verification failed")
            sys.exit(1)
    
    # 执行迁移
    success_count = 0
    for table_name in table_names:
        if migrate_table(source_engine, target_engine, table_name, args.incremental, args.where):
            success_count += 1
    
    safe_print(f"[INFO] Migration completed: {success_count}/{len(table_names)} tables succeeded")
    
    # 验证迁移
    if args.verify:
        if verify_migration(source_engine, target_engine, table_names):
            safe_print("[OK] Migration verified successfully")
        else:
            safe_print("[WARN] Migration verification failed (see details above)")
            sys.exit(1)
    
    if success_count == len(table_names):
        safe_print("[OK] All tables migrated successfully")
        sys.exit(0)
    else:
        safe_print(f"[ERROR] Some tables failed to migrate ({success_count}/{len(table_names)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
