#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库健康检查脚本

用途：
1. 检查所有 schema 是否存在
2. 检查关键表是否存在于正确的 schema
3. 检查重复表（同一表存在于多个 schema）
4. 检查表字段是否与 ORM 定义匹配
5. 给出修复建议

使用方法：
    python scripts/check_database_health.py

作者: AI Agent
日期: 2026-01-30
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


def safe_print(msg: str):
    """安全打印（避免 Windows 终端 Unicode 错误）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))


def get_database_url():
    """获取数据库连接 URL"""
    return os.getenv("DATABASE_URL", "postgresql://erp_user:erp_password@localhost:5432/xihong_erp")


def check_schemas_exist(conn) -> tuple:
    """检查所有必需的 schema 是否存在"""
    issues = []
    recommendations = []
    
    required_schemas = ["public", "a_class", "b_class", "c_class", "core", "finance"]
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT schema_name 
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    """)
    existing_schemas = {row[0] for row in cursor.fetchall()}
    cursor.close()
    
    safe_print("--- 检查 Schema ---")
    for schema in required_schemas:
        if schema in existing_schemas:
            safe_print(f"[OK] {schema} schema 存在")
        else:
            issues.append(f"[FAIL] {schema} schema 不存在")
            recommendations.append(f"创建 schema: CREATE SCHEMA IF NOT EXISTS {schema}")
    
    return issues, recommendations


def check_tables_in_schema(conn, table_name: str, expected_schema: str) -> tuple:
    """检查表是否在正确的 schema 中"""
    issues = []
    recommendations = []
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_schema 
        FROM information_schema.tables 
        WHERE table_name = %s
    """, (table_name,))
    found_schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()
    
    if expected_schema in found_schemas:
        safe_print(f"[OK] {expected_schema}.{table_name} 存在")
        # 检查是否有重复表
        if len(found_schemas) > 1:
            other_schemas = [s for s in found_schemas if s != expected_schema]
            issues.append(f"[WARN] {table_name} 表在多个 schema 中存在: {found_schemas}")
            recommendations.append(f"考虑删除重复表: {', '.join([f'{s}.{table_name}' for s in other_schemas])}")
    elif found_schemas:
        issues.append(f"[FAIL] {table_name} 表存在于 {found_schemas}，但应该在 {expected_schema}")
        recommendations.append(f"移动表到正确的 schema，或更新 ORM 定义")
    else:
        issues.append(f"[FAIL] {table_name} 表不存在")
        recommendations.append(f"执行迁移创建表: alembic upgrade head")
    
    return issues, recommendations


def check_table_columns(conn, table_name: str, schema: str, expected_columns: list) -> tuple:
    """检查表字段是否与预期匹配"""
    issues = []
    recommendations = []
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = %s AND table_name = %s
    """, (schema, table_name))
    actual_columns = {row[0] for row in cursor.fetchall()}
    cursor.close()
    
    if not actual_columns:
        issues.append(f"[FAIL] 无法获取 {schema}.{table_name} 的字段信息")
        return issues, recommendations
    
    missing_columns = set(expected_columns) - actual_columns
    if missing_columns:
        issues.append(f"[FAIL] {schema}.{table_name} 缺少字段: {missing_columns}")
        recommendations.append(f"执行迁移添加缺失字段")
    
    return issues, recommendations


def check_critical_tables(conn) -> tuple:
    """检查关键业务表"""
    issues = []
    recommendations = []
    
    safe_print("")
    safe_print("--- 检查关键表 ---")
    
    # 定义关键表及其期望的 schema
    critical_tables = [
        # (表名, 期望 schema, 期望字段列表)
        ("operating_costs", "a_class", ["id", "店铺ID", "年月", "租金", "工资", "水电费", "其他成本", "创建时间", "更新时间"]),
        ("sales_targets", "a_class", ["id", "target_name", "target_type", "period_start", "period_end"]),
        ("sales_targets_a", "a_class", []),  # A 类数据表
        ("target_breakdown", "a_class", ["id", "target_id", "breakdown_type"]),
        ("platform_accounts", "core", ["id", "platform", "account_alias"]),
        ("employees", "a_class", ["id", "employee_code", "name"]),
        ("departments", "a_class", ["id", "department_code", "department_name"]),
    ]
    
    for table_name, expected_schema, expected_columns in critical_tables:
        table_issues, table_recs = check_tables_in_schema(conn, table_name, expected_schema)
        issues.extend(table_issues)
        recommendations.extend(table_recs)
        
        # 检查字段（如果表存在且有期望字段列表）
        if expected_columns and not any("[FAIL]" in i and "不存在" in i for i in table_issues):
            col_issues, col_recs = check_table_columns(conn, table_name, expected_schema, expected_columns)
            issues.extend(col_issues)
            recommendations.extend(col_recs)
    
    return issues, recommendations


def check_duplicate_tables(conn) -> tuple:
    """检查重复表（同一表名存在于多个 schema）"""
    issues = []
    recommendations = []
    
    safe_print("")
    safe_print("--- 检查重复表 ---")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_name, array_agg(table_schema) as schemas
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        GROUP BY table_name
        HAVING COUNT(DISTINCT table_schema) > 1
    """)
    duplicates = cursor.fetchall()
    cursor.close()
    
    if duplicates:
        for table_name, schemas in duplicates:
            schemas_list = list(schemas)
            issues.append(f"[WARN] 重复表: {table_name} 存在于 {schemas_list}")
            # 尝试确定哪个是正确的
            if "a_class" in schemas_list and any(s in schemas_list for s in ["public", "core"]):
                primary = "a_class" if table_name.endswith("_a") or table_name in ["operating_costs", "employees", "departments", "target_breakdown"] else "public"
                others = [s for s in schemas_list if s != primary]
                recommendations.append(f"保留 {primary}.{table_name}，考虑删除: {', '.join([f'{s}.{table_name}' for s in others])}")
        safe_print(f"[WARN] 发现 {len(duplicates)} 个重复表")
    else:
        safe_print("[OK] 无重复表")
    
    return issues, recommendations


def check_search_path(conn) -> tuple:
    """检查数据库 search_path 设置"""
    issues = []
    recommendations = []
    
    safe_print("")
    safe_print("--- 检查 Search Path ---")
    
    cursor = conn.cursor()
    cursor.execute("SHOW search_path")
    search_path = cursor.fetchone()[0]
    cursor.close()
    
    safe_print(f"[INFO] 当前 search_path: {search_path}")
    
    required_schemas = ["public", "a_class", "b_class", "c_class", "core"]
    for schema in required_schemas:
        if schema not in search_path:
            issues.append(f"[WARN] search_path 中缺少 {schema}")
    
    return issues, recommendations


def main():
    """主函数"""
    safe_print("=" * 70)
    safe_print("数据库健康检查工具")
    safe_print("=" * 70)
    safe_print("")
    
    # 获取数据库连接
    database_url = get_database_url()
    safe_print(f"[INFO] 数据库: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    safe_print("")
    
    try:
        import psycopg2
    except ImportError:
        safe_print("[FAIL] 缺少 psycopg2 库，请安装: pip install psycopg2-binary")
        return 1
    
    try:
        conn = psycopg2.connect(database_url)
        safe_print("[OK] 数据库连接成功")
    except Exception as e:
        safe_print(f"[FAIL] 数据库连接失败: {e}")
        return 1
    
    all_issues = []
    all_recommendations = []
    
    # 1. 检查 schema
    issues, recs = check_schemas_exist(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recs)
    
    # 2. 检查关键表
    issues, recs = check_critical_tables(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recs)
    
    # 3. 检查重复表
    issues, recs = check_duplicate_tables(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recs)
    
    # 4. 检查 search_path
    issues, recs = check_search_path(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recs)
    
    conn.close()
    
    # 汇总
    safe_print("")
    safe_print("=" * 70)
    safe_print("诊断结果汇总")
    safe_print("=" * 70)
    
    fail_count = sum(1 for i in all_issues if "[FAIL]" in i)
    warn_count = sum(1 for i in all_issues if "[WARN]" in i)
    
    if fail_count == 0 and warn_count == 0:
        safe_print("[OK] 所有检查通过，数据库结构健康")
        return 0
    
    if fail_count > 0:
        safe_print(f"[FAIL] 发现 {fail_count} 个严重问题:")
        for issue in all_issues:
            if "[FAIL]" in issue:
                safe_print(f"  {issue}")
        safe_print("")
    
    if warn_count > 0:
        safe_print(f"[WARN] 发现 {warn_count} 个警告:")
        for issue in all_issues:
            if "[WARN]" in issue:
                safe_print(f"  {issue}")
        safe_print("")
    
    if all_recommendations:
        safe_print("修复建议:")
        for rec in set(all_recommendations):  # 去重
            safe_print(f"  - {rec}")
    
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
