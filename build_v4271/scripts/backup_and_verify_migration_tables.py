#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表迁移备份与验证脚本

用途：
1. 在迁移前备份关键表数据到 JSON 文件
2. 验证备份数据完整性（行数、空值率、抽样记录）
3. 支持从备份恢复数据并验证一致性

使用方式：
  # 备份表数据
  python scripts/backup_and_verify_migration_tables.py backup --table sales_targets --schema a_class
  
  # 验证备份完整性
  python scripts/backup_and_verify_migration_tables.py verify --backup-file backups/sales_targets_20260317.json
  
  # 从备份恢复（需谨慎）
  python scripts/backup_and_verify_migration_tables.py restore --backup-file backups/sales_targets_20260317.json --schema a_class
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import get_sync_engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


def backup_table(
    table_name: str,
    schema: str = "public",
    output_dir: str = "backups"
) -> Path:
    """
    备份指定表的数据到 JSON 文件
    
    Returns:
        备份文件路径
    """
    engine = get_sync_engine()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = output_path / f"{schema}_{table_name}_{timestamp}.json"
    
    with engine.connect() as conn:
        # 检查表是否存在
        check_sql = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :table
            )
        """)
        exists = conn.execute(check_sql, {"schema": schema, "table": table_name}).scalar()
        
        if not exists:
            logger.error(f"[FAIL] Table {schema}.{table_name} does not exist")
            sys.exit(1)
        
        # 查询所有数据
        query_sql = text(f'SELECT * FROM "{schema}"."{table_name}"')
        result = conn.execute(query_sql)
        
        # 获取列名
        columns = result.keys()
        
        # 转换为字典列表
        rows = []
        for row in result:
            row_dict = {}
            for col, val in zip(columns, row):
                # 处理特殊类型
                if isinstance(val, datetime):
                    row_dict[col] = val.isoformat()
                elif val is None:
                    row_dict[col] = None
                else:
                    row_dict[col] = val
            rows.append(row_dict)
        
        # 计算统计信息
        total_rows = len(rows)
        null_rates = {}
        if total_rows > 0:
            for col in columns:
                null_count = sum(1 for row in rows if row[col] is None)
                null_rates[col] = round(null_count / total_rows * 100, 2)
        
        # 保存备份
        backup_data = {
            "metadata": {
                "table_name": table_name,
                "schema": schema,
                "backup_time": datetime.now(timezone.utc).isoformat(),
                "total_rows": total_rows,
                "columns": list(columns),
                "null_rates": null_rates
            },
            "data": rows
        }
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[OK] Backup completed: {backup_file}")
        logger.info(f"[INFO] Total rows: {total_rows}")
        logger.info(f"[INFO] Columns: {len(columns)}")
        
        return backup_file


def verify_backup(backup_file: Path) -> bool:
    """
    验证备份文件完整性
    
    Returns:
        True if verification passed
    """
    if not backup_file.exists():
        logger.error(f"[FAIL] Backup file not found: {backup_file}")
        return False
    
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
        
        metadata = backup_data["metadata"]
        data = backup_data["data"]
        
        logger.info(f"[INFO] Verifying backup: {backup_file}")
        logger.info(f"[INFO] Table: {metadata['schema']}.{metadata['table_name']}")
        logger.info(f"[INFO] Backup time: {metadata['backup_time']}")
        logger.info(f"[INFO] Total rows: {metadata['total_rows']}")
        
        # 验证数据行数一致
        if len(data) != metadata["total_rows"]:
            logger.error(f"[FAIL] Row count mismatch: expected {metadata['total_rows']}, got {len(data)}")
            return False
        
        # 验证列完整性
        if data:
            first_row_cols = set(data[0].keys())
            expected_cols = set(metadata["columns"])
            if first_row_cols != expected_cols:
                logger.error(f"[FAIL] Column mismatch")
                logger.error(f"  Expected: {expected_cols}")
                logger.error(f"  Got: {first_row_cols}")
                return False
        
        # 抽样验证（前5条、后5条、中间10条）
        sample_indices = []
        if len(data) > 0:
            sample_indices.extend(range(min(5, len(data))))  # 前5条
            if len(data) > 10:
                mid = len(data) // 2
                sample_indices.extend(range(mid - 5, mid + 5))  # 中间10条
            if len(data) > 5:
                sample_indices.extend(range(max(0, len(data) - 5), len(data)))  # 后5条
        
        logger.info(f"[INFO] Sample verification: {len(set(sample_indices))} rows")
        
        for idx in set(sample_indices):
            row = data[idx]
            # 验证每行都有完整的列
            if set(row.keys()) != set(metadata["columns"]):
                logger.error(f"[FAIL] Row {idx} has incomplete columns")
                return False
        
        logger.info("[OK] Backup verification passed")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Verification failed: {e}", exc_info=True)
        return False


def restore_from_backup(
    backup_file: Path,
    target_schema: str,
    dry_run: bool = True
) -> bool:
    """
    从备份恢复数据（谨慎使用）
    
    Args:
        backup_file: 备份文件路径
        target_schema: 目标 schema
        dry_run: 是否仅模拟运行
    
    Returns:
        True if restore succeeded
    """
    if not backup_file.exists():
        logger.error(f"[FAIL] Backup file not found: {backup_file}")
        return False
    
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
        
        metadata = backup_data["metadata"]
        data = backup_data["data"]
        table_name = metadata["table_name"]
        
        logger.info(f"[INFO] {'[DRY RUN] ' if dry_run else ''}Restoring from backup: {backup_file}")
        logger.info(f"[INFO] Target: {target_schema}.{table_name}")
        logger.info(f"[INFO] Rows to restore: {len(data)}")
        
        if dry_run:
            logger.info("[INFO] Dry run mode - no actual changes will be made")
            return True
        
        engine = get_sync_engine()
        
        with engine.begin() as conn:
            # 检查目标表是否存在
            check_sql = text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = :schema AND table_name = :table
                )
            """)
            exists = conn.execute(check_sql, {"schema": target_schema, "table": table_name}).scalar()
            
            if not exists:
                logger.error(f"[FAIL] Target table {target_schema}.{table_name} does not exist")
                return False
            
            # 清空目标表（谨慎！）
            logger.warning(f"[WARN] Truncating {target_schema}.{table_name}")
            conn.execute(text(f'TRUNCATE TABLE "{target_schema}"."{table_name}" CASCADE'))
            
            # 批量插入数据
            if data:
                columns = metadata["columns"]
                placeholders = ", ".join([f":{col}" for col in columns])
                insert_sql = text(
                    f'INSERT INTO "{target_schema}"."{table_name}" '
                    f'({", ".join([f\'"{col}"\' for col in columns])}) '
                    f'VALUES ({placeholders})'
                )
                
                for row in data:
                    conn.execute(insert_sql, row)
            
            logger.info(f"[OK] Restored {len(data)} rows to {target_schema}.{table_name}")
            return True
        
    except Exception as e:
        logger.error(f"[FAIL] Restore failed: {e}", exc_info=True)
        return False


def compare_with_current(backup_file: Path, schema: str) -> bool:
    """
    将备份数据与当前数据库表对比
    
    Returns:
        True if comparison passed
    """
    if not backup_file.exists():
        logger.error(f"[FAIL] Backup file not found: {backup_file}")
        return False
    
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
        
        metadata = backup_data["metadata"]
        backup_rows = backup_data["data"]
        table_name = metadata["table_name"]
        
        logger.info(f"[INFO] Comparing backup with current table: {schema}.{table_name}")
        
        engine = get_sync_engine()
        
        with engine.connect() as conn:
            # 查询当前数据
            query_sql = text(f'SELECT * FROM "{schema}"."{table_name}"')
            result = conn.execute(query_sql)
            
            current_rows = []
            for row in result:
                row_dict = {}
                for col, val in zip(result.keys(), row):
                    if isinstance(val, datetime):
                        row_dict[col] = val.isoformat()
                    else:
                        row_dict[col] = val
                current_rows.append(row_dict)
            
            # 对比行数
            logger.info(f"[INFO] Backup rows: {len(backup_rows)}")
            logger.info(f"[INFO] Current rows: {len(current_rows)}")
            
            if len(backup_rows) != len(current_rows):
                logger.warning(f"[WARN] Row count mismatch")
                return False
            
            # 对比空值率
            if current_rows:
                for col in metadata["columns"]:
                    backup_null_rate = metadata["null_rates"].get(col, 0)
                    current_null_count = sum(1 for row in current_rows if row.get(col) is None)
                    current_null_rate = round(current_null_count / len(current_rows) * 100, 2)
                    
                    if abs(backup_null_rate - current_null_rate) > 1.0:  # 允许1%误差
                        logger.warning(
                            f"[WARN] Null rate mismatch for column '{col}': "
                            f"backup={backup_null_rate}%, current={current_null_rate}%"
                        )
            
            # 抽样对比（前20条）
            sample_size = min(20, len(backup_rows))
            logger.info(f"[INFO] Sampling {sample_size} rows for comparison")
            
            for i in range(sample_size):
                backup_row = backup_rows[i]
                current_row = current_rows[i]
                
                # 对比关键字段（假设第一列是 ID）
                id_col = metadata["columns"][0]
                if backup_row.get(id_col) != current_row.get(id_col):
                    logger.warning(f"[WARN] Row {i} ID mismatch")
            
            logger.info("[OK] Comparison completed")
            return True
        
    except Exception as e:
        logger.error(f"[FAIL] Comparison failed: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="数据库表迁移备份与验证工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # backup 子命令
    backup_parser = subparsers.add_parser("backup", help="备份表数据")
    backup_parser.add_argument("--table", required=True, help="表名")
    backup_parser.add_argument("--schema", default="public", help="Schema 名称")
    backup_parser.add_argument("--output-dir", default="backups", help="输出目录")
    
    # verify 子命令
    verify_parser = subparsers.add_parser("verify", help="验证备份完整性")
    verify_parser.add_argument("--backup-file", required=True, help="备份文件路径")
    
    # restore 子命令
    restore_parser = subparsers.add_parser("restore", help="从备份恢复数据")
    restore_parser.add_argument("--backup-file", required=True, help="备份文件路径")
    restore_parser.add_argument("--schema", required=True, help="目标 schema")
    restore_parser.add_argument("--dry-run", action="store_true", help="仅模拟运行")
    
    # compare 子命令
    compare_parser = subparsers.add_parser("compare", help="对比备份与当前数据")
    compare_parser.add_argument("--backup-file", required=True, help="备份文件路径")
    compare_parser.add_argument("--schema", required=True, help="当前表所在 schema")
    
    args = parser.parse_args()
    
    if args.command == "backup":
        backup_file = backup_table(args.table, args.schema, args.output_dir)
        # 自动验证备份
        verify_backup(backup_file)
        
    elif args.command == "verify":
        success = verify_backup(Path(args.backup_file))
        sys.exit(0 if success else 1)
        
    elif args.command == "restore":
        success = restore_from_backup(Path(args.backup_file), args.schema, args.dry_run)
        sys.exit(0 if success else 1)
        
    elif args.command == "compare":
        success = compare_with_current(Path(args.backup_file), args.schema)
        sys.exit(0 if success else 1)
        
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
