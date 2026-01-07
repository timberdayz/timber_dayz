#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表完整迁移脚本（Complete Tables Migration）

功能：
1. 根据分类建议迁移所有剩余表到对应schema
2. 支持按schema分组迁移（core, a_class, c_class, finance）
3. 自动处理重复表和空表
4. 支持dry-run模式（预览迁移计划）
5. 生成详细迁移报告

分类规则：
- core: 维度表和管理表
- a_class: 用户输入数据表
- c_class: 计算输出表
- finance: 财务域表

注意：
- 本脚本连接Docker PostgreSQL数据库
- 默认dry-run模式，只显示迁移计划
- 使用--execute参数才会实际执行迁移
- 迁移前建议备份数据库
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


# ==================== 表分类定义 ====================

# core Schema - 维度表和管理表
CORE_DIMENSION_TABLES = [
    "dim_platforms",
    "dim_shops",
    "dim_products",
    "dim_product_master",
    "bridge_product_keys",
    "dim_currency_rates",
    "dim_exchange_rates",
    "dim_currencies",
    "dim_fiscal_calendar",
    "dim_date",
    "dim_vendors",
    "dim_roles",
    "dim_users",
]

CORE_MANAGEMENT_TABLES = [
    "account_aliases",
    "field_mapping_templates",
    "field_mapping_template_items",
    "field_mapping_audit",
    "field_mappings",  # 旧表，可能废弃
    "field_usage_tracking",
    "staging_inventory",
]

# a_class Schema - 用户输入数据表
A_CLASS_TABLES = [
    "sales_campaigns",  # 旧表，a_class已有sales_campaigns_a
    "sales_campaign_shops",
    "campaign_targets",
    "target_breakdown",
    "sales_targets",  # 旧表，a_class已有sales_targets_a
    "employee_targets",  # a_class已有，可能是重复
    "employees",  # a_class已有，可能是重复
    "attendance_records",  # a_class已有，可能是重复
    "operating_costs",  # a_class已有，可能是重复
    "performance_config",  # 旧表，a_class已有performance_config_a
    "performance_config_a",  # a_class已有，可能是重复
]

# c_class Schema - 计算输出表
C_CLASS_TABLES = [
    "employee_performance",  # c_class已有，可能是重复
    "employee_commissions",  # c_class已有，可能是重复
    "shop_commissions",  # c_class已有，可能是重复
    "performance_scores",  # 旧表，c_class已有performance_scores_c
    "performance_scores_c",  # c_class已有，可能是重复
    "shop_health_scores",
    "clearance_rankings",
]

# finance Schema - 财务域表
FINANCE_TABLES = [
    "po_headers",
    "po_lines",
    "grn_headers",
    "grn_lines",
    "invoice_headers",
    "invoice_lines",
    "invoice_attachments",
    "fact_expenses_month",
    "fact_expenses_allocated_day_shop_sku",
    "allocation_rules",
    "logistics_costs",
    "logistics_allocation_rules",
    "inventory_ledger",
    "opening_balances",
    "gl_accounts",
    "journal_entries",
    "journal_entry_lines",
    "fx_rates",
    "tax_vouchers",
    "tax_reports",
    "three_way_match_log",
    "approval_logs",
    "return_orders",
]

# 表分类映射
TABLE_MIGRATION_MAP = {
    "core": CORE_DIMENSION_TABLES + CORE_MANAGEMENT_TABLES,
    "a_class": A_CLASS_TABLES,
    "c_class": C_CLASS_TABLES,
    "finance": FINANCE_TABLES,
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


def get_table_row_count(conn, schema: str, table_name: str) -> int:
    """获取表的行数"""
    try:
        query = text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
        result = conn.execute(query).scalar()
        return result or 0
    except:
        return -1


def check_and_handle_duplicate_table(conn, table_name: str, target_schema: str, dry_run: bool = True) -> Tuple[bool, str]:
    """检查并处理重复表（目标schema中已存在同名表）"""
    # 检查目标schema中是否有同名表
    if not check_table_exists(conn, target_schema, table_name):
        return True, "no_duplicate"  # 没有重复，可以继续
    
    # 检查目标schema中的表是否为空
    try:
        target_count = get_table_row_count(conn, target_schema, table_name)
        current_schema = get_table_schema(conn, table_name)
        current_count = get_table_row_count(conn, current_schema, table_name) if current_schema else 0
        
        if target_count > 0:
            return False, f"target_has_data_{target_count}_rows"  # 目标表有数据，需要手动处理
        
        # 目标表是空的，可以删除
        if dry_run:
            return True, "will_drop_empty_target"
        else:
            drop_sql = text(f'DROP TABLE "{target_schema}"."{table_name}"')
            conn.execute(drop_sql)
            conn.commit()
            return True, "dropped_empty_target"
    except Exception as e:
        return False, f"error_checking_{str(e)}"


def analyze_migration_plan(conn) -> Dict:
    """分析迁移计划"""
    plan = {
        "schemas": {
            "core": {"tables_to_migrate": [], "tables_already_there": [], "tables_not_found": [], "tables_with_duplicates": []},
            "a_class": {"tables_to_migrate": [], "tables_already_there": [], "tables_not_found": [], "tables_with_duplicates": []},
            "c_class": {"tables_to_migrate": [], "tables_already_there": [], "tables_not_found": [], "tables_with_duplicates": []},
            "finance": {"tables_to_migrate": [], "tables_already_there": [], "tables_not_found": [], "tables_with_duplicates": []},
        },
    }
    
    for target_schema, table_list in TABLE_MIGRATION_MAP.items():
        for table_name in table_list:
            current_schema = get_table_schema(conn, table_name)
            
            if current_schema is None:
                plan["schemas"][target_schema]["tables_not_found"].append(table_name)
                continue
            
            if current_schema == target_schema:
                plan["schemas"][target_schema]["tables_already_there"].append(table_name)
                continue
            
            # 检查目标schema中是否有重复表
            if check_table_exists(conn, target_schema, table_name):
                target_count = get_table_row_count(conn, target_schema, table_name)
                current_count = get_table_row_count(conn, current_schema, table_name)
                plan["schemas"][target_schema]["tables_with_duplicates"].append({
                    "table": table_name,
                    "current_schema": current_schema,
                    "target_schema": target_schema,
                    "target_count": target_count,
                    "current_count": current_count,
                })
                continue
            
            plan["schemas"][target_schema]["tables_to_migrate"].append({
                "table": table_name,
                "current_schema": current_schema,
                "target_schema": target_schema,
            })
    
    return plan


def print_migration_plan(plan: Dict):
    """打印迁移计划"""
    print("\n" + "=" * 80)
    print("数据库表完整迁移计划")
    print("=" * 80)
    
    total_to_migrate = 0
    total_duplicates = 0
    
    for schema_name, schema_plan in plan["schemas"].items():
        if not any([schema_plan["tables_to_migrate"], schema_plan["tables_with_duplicates"]]):
            continue
        
        print(f"\n[{schema_name.upper()} Schema]")
        print("-" * 80)
        
        # 需要迁移的表
        if schema_plan["tables_to_migrate"]:
            print(f"\n  需要迁移的表 ({len(schema_plan['tables_to_migrate'])} 张):")
            for item in schema_plan["tables_to_migrate"]:
                print(f"    {item['current_schema']}.{item['table']} -> {item['target_schema']}.{item['table']}")
            total_to_migrate += len(schema_plan["tables_to_migrate"])
        
        # 重复表
        if schema_plan["tables_with_duplicates"]:
            print(f"\n  重复表 ({len(schema_plan['tables_with_duplicates'])} 张):")
            for item in schema_plan["tables_with_duplicates"]:
                status = "空表，将自动删除" if item["target_count"] == 0 else f"有{item['target_count']}行数据，需要手动处理"
                print(f"    {item['current_schema']}.{item['table']} (目标: {item['target_schema']}.{item['table']}) - {status}")
            total_duplicates += len(schema_plan["tables_with_duplicates"])
        
        # 已在目标schema的表
        if schema_plan["tables_already_there"]:
            print(f"\n  已在{schema_name} schema的表 ({len(schema_plan['tables_already_there'])} 张):")
            for table in schema_plan["tables_already_there"][:5]:  # 只显示前5个
                print(f"    {schema_name}.{table}")
            if len(schema_plan["tables_already_there"]) > 5:
                print(f"    ... 还有 {len(schema_plan['tables_already_there']) - 5} 张表")
        
        # 未找到的表
        if schema_plan["tables_not_found"]:
            print(f"\n  未找到的表 ({len(schema_plan['tables_not_found'])} 张):")
            for table in schema_plan["tables_not_found"][:5]:  # 只显示前5个
                print(f"    {table}")
            if len(schema_plan["tables_not_found"]) > 5:
                print(f"    ... 还有 {len(schema_plan['tables_not_found']) - 5} 张表")
    
    print("\n" + "=" * 80)
    print(f"总计: 需要迁移 {total_to_migrate} 张表, 发现 {total_duplicates} 张重复表")
    print("=" * 80)


def execute_migration(conn, plan: Dict, dry_run: bool = True) -> Dict:
    """执行迁移"""
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
        "dropped": [],
    }
    
    # 按schema顺序执行迁移
    schema_order = ["core", "a_class", "c_class", "finance"]
    
    for schema_name in schema_order:
        schema_plan = plan["schemas"][schema_name]
        
        # 处理重复表（先删除空的重复表）
        if schema_plan["tables_with_duplicates"]:
            print(f"\n[处理] {schema_name} schema 的重复表...")
            print("-" * 80)
            for item in schema_plan["tables_with_duplicates"]:
                table_name = item["table"]
                target_schema = item["target_schema"]
                
                if item["target_count"] > 0:
                    print(f"  [跳过] {target_schema}.{table_name} 有 {item['target_count']} 行数据，需要手动处理")
                    results["skipped"].append(item)
                    continue
                
                # 目标表是空的，可以删除
                can_migrate, status = check_and_handle_duplicate_table(conn, table_name, target_schema, dry_run)
                if can_migrate:
                    if "dropped" in status or "will_drop" in status:
                        print(f"  [{'DRY-RUN: ' if dry_run else ''}删除] 空的 {target_schema}.{table_name} 表")
                        if not dry_run:
                            results["dropped"].append(item)
                    # 删除成功后，添加到迁移列表
                    schema_plan["tables_to_migrate"].append({
                        "table": table_name,
                        "current_schema": item["current_schema"],
                        "target_schema": target_schema,
                    })
                else:
                    results["skipped"].append(item)
        
        # 执行迁移
        if schema_plan["tables_to_migrate"]:
            print(f"\n[执行] 迁移 {schema_name} schema 的表 ({len(schema_plan['tables_to_migrate'])} 张)...")
            print("-" * 80)
            
            for item in schema_plan["tables_to_migrate"]:
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
        for item in results["success"][:10]:  # 只显示前10个
            print(f"  {item['current_schema']}.{item['table']} -> {item['target_schema']}.{item['table']}")
        if len(results["success"]) > 10:
            print(f"  ... 还有 {len(results['success']) - 10} 张表")
    
    if results["dropped"]:
        print(f"\n[删除] {len(results['dropped'])} 张空表")
        for item in results["dropped"][:5]:
            print(f"  {item['target_schema']}.{item['table']}")
        if len(results["dropped"]) > 5:
            print(f"  ... 还有 {len(results['dropped']) - 5} 张表")
    
    if results["failed"]:
        print(f"\n[失败] {len(results['failed'])} 张表")
        for item in results["failed"]:
            print(f"  {item['current_schema']}.{item['table']}: {item.get('error', 'Unknown error')}")
    
    if results["skipped"]:
        print(f"\n[跳过] {len(results['skipped'])} 张表（需要手动处理）")
        for item in results["skipped"][:5]:
            print(f"  {item['current_schema']}.{item['table']} -> {item['target_schema']}.{item['table']} (目标表有数据)")
        if len(results["skipped"]) > 5:
            print(f"  ... 还有 {len(results['skipped']) - 5} 张表")
    
    print("\n" + "=" * 80)


def ensure_schema_exists(conn, schema_name: str, dry_run: bool = True) -> bool:
    """确保schema存在"""
    query = text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name = :schema_name
    """)
    result = conn.execute(query, {"schema_name": schema_name}).fetchone()
    
    if result:
        return True  # schema已存在
    
    if dry_run:
        print(f"  [DRY-RUN] 将创建 schema: {schema_name}")
        return True
    else:
        try:
            create_sql = text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
            conn.execute(create_sql)
            conn.commit()
            print(f"  [创建] schema: {schema_name}")
            return True
        except Exception as e:
            print(f"  [失败] 创建schema {schema_name}: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="数据库表完整迁移脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行迁移（默认是dry-run模式）"
    )
    parser.add_argument(
        "--schema",
        type=str,
        choices=["core", "a_class", "c_class", "finance", "all"],
        default="all",
        help="指定要迁移的schema（默认：all）"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("数据库表完整迁移脚本")
    print("=" * 80)
    print(f"模式: {'执行模式' if args.execute else '预览模式 (dry-run)'}")
    print(f"目标Schema: {args.schema}")
    
    # 连接数据库
    with engine.connect() as conn:
        # 确保所有schema存在
        print("\n[检查] 确保所有schema存在...")
        print("-" * 80)
        schemas_to_check = ["core", "a_class", "c_class", "finance"] if args.schema == "all" else [args.schema]
        for schema_name in schemas_to_check:
            ensure_schema_exists(conn, schema_name, dry_run=not args.execute)
        
        # 分析迁移计划
        plan = analyze_migration_plan(conn)
        
        # 如果指定了特定schema，只显示该schema的计划
        if args.schema != "all":
            for key in plan["schemas"].keys():
                if key != args.schema:
                    plan["schemas"][key] = {"tables_to_migrate": [], "tables_already_there": [], "tables_not_found": [], "tables_with_duplicates": []}
        
        # 打印迁移计划
        print_migration_plan(plan)
        
        # 检查是否有需要手动处理的重复表（有数据的）
        has_data_duplicates = False
        for schema_plan in plan["schemas"].values():
            for item in schema_plan["tables_with_duplicates"]:
                if item.get("target_count", 0) > 0:
                    has_data_duplicates = True
                    break
        
        if has_data_duplicates and not args.execute:
            print("\n[警告] 发现目标schema中有数据的重复表，需要手动处理")
        
        # 执行迁移
        total_to_migrate = sum(len(s["tables_to_migrate"]) for s in plan["schemas"].values())
        if total_to_migrate > 0 or any(s["tables_with_duplicates"] for s in plan["schemas"].values()):
            results = execute_migration(conn, plan, dry_run=not args.execute)
            print_migration_results(results)
            
            if args.execute and results["success"]:
                print("\n[提示] 迁移完成，请验证相关功能")
        else:
            print("\n[信息] 没有需要迁移的表")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

