#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心功能表迁移脚本（Core Tables Migration）

功能：
1. 迁移核心功能表到core schema（账号密码、数据同步相关表）
2. 支持dry-run模式（预览迁移计划）
3. 检查表是否存在、是否已在目标schema
4. 自动处理外键依赖
5. 生成详细迁移报告

核心功能表（必须迁移）：
- platform_accounts: 账号密码管理
- catalog_files: 数据同步核心表
- collection_tasks: 采集任务管理
- sync_progress_tasks: 同步进度跟踪
- collection_configs: 采集配置
- component_versions: 组件版本管理
- component_test_history: 组件测试历史

注意：
- 本脚本连接Docker PostgreSQL数据库
- 默认dry-run模式，只显示迁移计划
- 使用--execute参数才会实际执行迁移
- 迁移后立即验证核心功能（账号登录、数据同步）
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError

from backend.models.database import engine, SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


# ==================== 核心功能表定义 ====================

# 核心功能表（必须迁移到core schema）
CORE_FUNCTIONAL_TABLES = [
    # 账号密码管理
    "platform_accounts",
    "accounts",  # 旧表，如果core中没有重复则迁移
    
    # 数据同步核心表
    "catalog_files",
    "collection_tasks",
    "sync_progress_tasks",
    "collection_configs",
    
    # 组件管理
    "component_versions",
    "component_test_history",
    
    # 其他核心管理表
    "collection_task_logs",  # 依赖collection_tasks
    "collection_sync_points",  # 采集同步点
]

# 表迁移优先级（考虑外键依赖）
MIGRATION_PRIORITY = {
    # 第一优先级：无依赖的表
    1: [
        "platform_accounts",
        "accounts",
        "component_versions",
        "collection_configs",
    ],
    # 第二优先级：被其他表依赖的表
    2: [
        "catalog_files",  # 被多个表引用
        "collection_tasks",  # 被collection_task_logs引用
    ],
    # 第三优先级：依赖其他表的表
    3: [
        "collection_task_logs",  # 依赖collection_tasks
        "sync_progress_tasks",
        "component_test_history",
        "collection_sync_points",
    ],
}


def get_table_schema(conn, table_name: str) -> Optional[str]:
    """获取表所在的schema"""
    query = text("""
        SELECT table_schema
        FROM information_schema.tables
        WHERE table_name = :table_name
        AND table_schema NOT IN ('pg_catalog', 'information_schema')
        LIMIT 1
    """)
    result = conn.execute(query, {"table_name": table_name}).fetchone()
    return result[0] if result else None


def check_table_exists(conn, schema: str, table_name: str) -> bool:
    """检查表是否存在"""
    query = text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = :schema
        AND table_name = :table_name
    """)
    result = conn.execute(query, {"schema": schema, "table_name": table_name}).scalar()
    return result > 0


def get_foreign_key_dependencies(conn, table_name: str) -> List[Dict]:
    """获取表的外键依赖关系"""
    query = text("""
        SELECT
            tc.constraint_name,
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_name = :table_name
        AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    """)
    result = conn.execute(query, {"table_name": table_name}).fetchall()
    return [
        {
            "constraint_name": row[0],
            "table_schema": row[1],
            "table_name": row[2],
            "column_name": row[3],
            "foreign_table_schema": row[4],
            "foreign_table_name": row[5],
            "foreign_column_name": row[6],
        }
        for row in result
    ]


def analyze_migration_plan(conn) -> Dict:
    """分析迁移计划"""
    plan = {
        "tables_to_migrate": [],
        "tables_already_in_core": [],
        "tables_not_found": [],
        "tables_with_duplicates": [],
        "foreign_key_impact": defaultdict(list),
    }
    
    for table_name in CORE_FUNCTIONAL_TABLES:
        current_schema = get_table_schema(conn, table_name)
        
        if current_schema is None:
            plan["tables_not_found"].append(table_name)
            continue
        
        if current_schema == "core":
            plan["tables_already_in_core"].append(table_name)
            continue
        
        # 检查core schema中是否有同名表
        if check_table_exists(conn, "core", table_name):
            plan["tables_with_duplicates"].append({
                "table": table_name,
                "current_schema": current_schema,
                "target_schema": "core",
            })
            continue
        
        # 检查外键依赖
        fk_deps = get_foreign_key_dependencies(conn, table_name)
        if fk_deps:
            plan["foreign_key_impact"][table_name] = fk_deps
        
        plan["tables_to_migrate"].append({
            "table": table_name,
            "current_schema": current_schema,
            "target_schema": "core",
            "has_foreign_keys": len(fk_deps) > 0,
        })
    
    return plan


def print_migration_plan(plan: Dict):
    """打印迁移计划"""
    print("\n" + "=" * 80)
    print("核心功能表迁移计划")
    print("=" * 80)
    
    # 需要迁移的表
    if plan["tables_to_migrate"]:
        print("\n[迁移列表] 需要迁移的表：")
        print("-" * 80)
        for item in plan["tables_to_migrate"]:
            print(f"  {item['current_schema']}.{item['table']} -> core.{item['table']}")
            if item["has_foreign_keys"]:
                print(f"    [注意] 此表有外键依赖，PostgreSQL会自动处理")
    
    # 已在core的表
    if plan["tables_already_in_core"]:
        print("\n[跳过] 已在core schema的表：")
        print("-" * 80)
        for table in plan["tables_already_in_core"]:
            print(f"  core.{table}")
    
    # 未找到的表
    if plan["tables_not_found"]:
        print("\n[警告] 未找到的表（可能已删除）：")
        print("-" * 80)
        for table in plan["tables_not_found"]:
            print(f"  {table}")
    
    # 重复表
    if plan["tables_with_duplicates"]:
        print("\n[错误] 发现重复表（core schema中已存在同名表）：")
        print("-" * 80)
        for item in plan["tables_with_duplicates"]:
            print(f"  {item['current_schema']}.{item['table']} (目标: core.{item['table']})")
        print("\n[建议] 请先检查并处理重复表，避免数据冲突")
    
    # 外键影响
    if plan["foreign_key_impact"]:
        print("\n[外键依赖] 迁移后的外键影响：")
        print("-" * 80)
        for table, deps in plan["foreign_key_impact"].items():
            print(f"  {table}:")
            for dep in deps:
                print(f"    -> {dep['table_schema']}.{dep['table_name']}.{dep['column_name']}")
    
    print("\n" + "=" * 80)


def check_and_handle_duplicate_table(conn, table_name: str, dry_run: bool = True) -> bool:
    """检查并处理重复表（core中已存在同名表）"""
    # 检查core中是否有同名表
    if not check_table_exists(conn, "core", table_name):
        return True  # 没有重复，可以继续
    
    # 检查core中的表是否为空
    try:
        count_query = text(f'SELECT COUNT(*) FROM core."{table_name}"')
        core_count = conn.execute(count_query).scalar()
        
        if core_count > 0:
            print(f"  [警告] core.{table_name} 已有数据 ({core_count} 行)，需要手动处理")
            return False
        
        # core中的表是空的，可以删除
        if dry_run:
            print(f"  [DRY-RUN] 删除空的 core.{table_name} 表")
        else:
            drop_sql = text(f'DROP TABLE core."{table_name}"')
            conn.execute(drop_sql)
            conn.commit()
            print(f"  [删除] 已删除空的 core.{table_name} 表")
        
        return True
    except Exception as e:
        print(f"  [错误] 检查 core.{table_name} 时出错: {e}")
        return False


def execute_migration(conn, plan: Dict, dry_run: bool = True) -> Dict:
    """执行迁移"""
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
    }
    
    # 处理重复表（先删除core中的空表）
    if plan["tables_with_duplicates"]:
        print("\n[处理] 处理重复表（删除core中的空表）...")
        print("-" * 80)
        for item in plan["tables_with_duplicates"]:
            table_name = item["table"]
            if check_and_handle_duplicate_table(conn, table_name, dry_run):
                # 删除成功后，添加到迁移列表
                plan["tables_to_migrate"].append({
                    "table": table_name,
                    "current_schema": item["current_schema"],
                    "target_schema": item["target_schema"],
                    "has_foreign_keys": False,
                })
            else:
                results["skipped"].append(item)
    
    # 按优先级排序
    migration_order = []
    for priority in sorted(MIGRATION_PRIORITY.keys()):
        for table_name in MIGRATION_PRIORITY[priority]:
            # 查找迁移计划中的表
            for item in plan["tables_to_migrate"]:
                if item["table"] == table_name:
                    migration_order.append(item)
                    break
    
    # 添加其他未在优先级列表中的表
    for item in plan["tables_to_migrate"]:
        if item not in migration_order:
            migration_order.append(item)
    
    if not migration_order:
        print("\n[信息] 没有需要迁移的表")
        return results
    
    print(f"\n[执行] 开始迁移 {len(migration_order)} 张表...")
    print("-" * 80)
    
    for item in migration_order:
        table_name = item["table"]
        current_schema = item["current_schema"]
        target_schema = item["target_schema"]
        
        try:
            if dry_run:
                print(f"  [DRY-RUN] {current_schema}.{table_name} -> {target_schema}.{table_name}")
                results["success"].append(item)
            else:
                # 执行迁移
                sql = text(f'ALTER TABLE "{current_schema}"."{table_name}" SET SCHEMA "{target_schema}"')
                conn.execute(sql)
                conn.commit()
                print(f"  [成功] {current_schema}.{table_name} -> {target_schema}.{table_name}")
                results["success"].append(item)
        except Exception as e:
            error_msg = str(e)
            print(f"  [失败] {current_schema}.{table_name}: {error_msg}")
            results["failed"].append({
                **item,
                "error": error_msg,
            })
    
    return results


def print_migration_results(results: Dict):
    """打印迁移结果"""
    print("\n" + "=" * 80)
    print("迁移结果汇总")
    print("=" * 80)
    
    print(f"\n[成功] {len(results['success'])} 张表")
    if results["success"]:
        for item in results["success"]:
            print(f"  {item['current_schema']}.{item['table']} -> {item['target_schema']}.{item['table']}")
    
    if results["failed"]:
        print(f"\n[失败] {len(results['failed'])} 张表")
        for item in results["failed"]:
            print(f"  {item['current_schema']}.{item['table']}: {item.get('error', 'Unknown error')}")
    
    print("\n" + "=" * 80)


def verify_core_functionality(db: Session) -> Dict:
    """验证核心功能（迁移后）"""
    print("\n[验证] 检查核心功能表...")
    print("-" * 80)
    
    verification = {
        "platform_accounts": False,
        "catalog_files": False,
        "collection_tasks": False,
    }
    
    try:
        # 检查platform_accounts
        query = text("SELECT COUNT(*) FROM core.platform_accounts LIMIT 1")
        result = db.execute(query).scalar()
        verification["platform_accounts"] = result is not None
        print(f"  [{'OK' if verification['platform_accounts'] else 'FAIL'}] platform_accounts")
    except Exception as e:
        print(f"  [FAIL] platform_accounts: {e}")
    
    try:
        # 检查catalog_files
        query = text("SELECT COUNT(*) FROM core.catalog_files LIMIT 1")
        result = db.execute(query).scalar()
        verification["catalog_files"] = result is not None
        print(f"  [{'OK' if verification['catalog_files'] else 'FAIL'}] catalog_files")
    except Exception as e:
        print(f"  [FAIL] catalog_files: {e}")
    
    try:
        # 检查collection_tasks
        query = text("SELECT COUNT(*) FROM core.collection_tasks LIMIT 1")
        result = db.execute(query).scalar()
        verification["collection_tasks"] = result is not None
        print(f"  [{'OK' if verification['collection_tasks'] else 'FAIL'}] collection_tasks")
    except Exception as e:
        print(f"  [FAIL] collection_tasks: {e}")
    
    return verification


def main():
    parser = argparse.ArgumentParser(description="核心功能表迁移脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行迁移（默认是dry-run模式）"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="迁移后验证核心功能"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("核心功能表迁移脚本")
    print("=" * 80)
    print(f"模式: {'执行模式' if args.execute else '预览模式 (dry-run)'}")
    print(f"验证: {'是' if args.verify else '否'}")
    
    # 连接数据库
    with engine.connect() as conn:
        # 分析迁移计划
        plan = analyze_migration_plan(conn)
        
        # 打印迁移计划
        print_migration_plan(plan)
        
        # 检查重复表（如果有数据需要手动处理）
        if plan["tables_with_duplicates"]:
            print("\n[提示] 发现重复表，脚本会自动处理空的core表")
            # 检查是否有数据的重复表
            has_data_duplicates = False
            for item in plan["tables_with_duplicates"]:
                table_name = item["table"]
                try:
                    count_query = text(f'SELECT COUNT(*) FROM core."{table_name}"')
                    count = conn.execute(count_query).scalar()
                    if count > 0:
                        print(f"  [警告] core.{table_name} 有 {count} 行数据，需要手动处理")
                        has_data_duplicates = True
                except:
                    pass
            
            if has_data_duplicates:
                print("\n[错误] 发现core中有数据的重复表，请先手动处理后再执行迁移")
                return 1
        
        # 执行迁移
        if plan["tables_to_migrate"]:
            results = execute_migration(conn, plan, dry_run=not args.execute)
            print_migration_results(results)
            
            if args.execute and results["success"]:
                print("\n[提示] 迁移完成，请立即验证核心功能：")
                print("  1. 账号登录功能")
                print("  2. 数据同步功能")
                print("  3. 采集任务创建和执行")
                
                # 验证核心功能
                if args.verify:
                    db = SessionLocal()
                    try:
                        verify_core_functionality(db)
                    finally:
                        db.close()
        else:
            print("\n[信息] 没有需要迁移的表")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

