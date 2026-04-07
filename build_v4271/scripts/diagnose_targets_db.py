#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
目标管理数据库诊断脚本

用途：
1. 检查 sales_targets 表是否存在及结构是否正确
2. 检查 target_breakdown 表是否存在及结构是否正确
3. 检查 platform_accounts 表（用于店铺列表）
4. 给出修复建议

使用方法：
    python scripts/diagnose_targets_db.py

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


def check_table_exists(conn, table_name: str, schema: str = "public") -> bool:
    """检查表是否存在"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = %s
        )
    """, (schema, table_name))
    result = cursor.fetchone()[0]
    cursor.close()
    return result


def get_table_columns(conn, table_name: str, schema: str = "public") -> dict:
    """获取表的列信息"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (schema, table_name))
    columns = {}
    for row in cursor.fetchall():
        columns[row[0]] = {
            "data_type": row[1],
            "is_nullable": row[2],
            "column_default": row[3]
        }
    cursor.close()
    return columns


def diagnose_sales_targets(conn) -> tuple:
    """诊断 sales_targets 表"""
    issues = []
    recommendations = []
    
    # 期望的列（根据 schema.py 中的 SalesTarget 定义）
    expected_columns = {
        "id": "integer",
        "target_name": "character varying",
        "target_type": "character varying",
        "period_start": "date",
        "period_end": "date",
        "target_amount": "double precision",
        "target_quantity": "integer",
        "achieved_amount": "double precision",
        "achieved_quantity": "integer",
        "achievement_rate": "double precision",
        "status": "character varying",
        "description": "text",
        "created_by": "character varying",
        "created_at": "timestamp without time zone",
        "updated_at": "timestamp without time zone",
    }
    
    if not check_table_exists(conn, "sales_targets", "a_class"):
        issues.append("[FAIL] a_class.sales_targets 表不存在")
        recommendations.append("执行 Alembic 迁移: python -m alembic upgrade head")
        return issues, recommendations
    
    safe_print("[OK] a_class.sales_targets 表存在")
    
    # 检查列
    actual_columns = get_table_columns(conn, "sales_targets", "a_class")
    
    missing_columns = []
    for col_name, expected_type in expected_columns.items():
        if col_name not in actual_columns:
            missing_columns.append(col_name)
            issues.append(f"[FAIL] 缺少列: {col_name} ({expected_type})")
    
    if missing_columns:
        recommendations.append(f"缺少 {len(missing_columns)} 个必要列，请执行迁移:")
        recommendations.append("  方法1: python -m alembic upgrade head")
        recommendations.append("  方法2: python scripts/fix_sales_targets_columns_standalone.py")
    else:
        safe_print(f"[OK] sales_targets 表结构完整 ({len(actual_columns)} 列)")
    
    # 检查数据
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM a_class.sales_targets")
        count = cursor.fetchone()[0]
        safe_print(f"[INFO] sales_targets 表当前有 {count} 条记录")
    except Exception as e:
        issues.append(f"[FAIL] 查询 sales_targets 失败: {e}")
    finally:
        cursor.close()
    
    return issues, recommendations


def diagnose_target_breakdown(conn) -> tuple:
    """诊断 target_breakdown 表"""
    issues = []
    recommendations = []
    
    # 检查多个可能的 schema
    found_schema = None
    for schema in ["a_class", "public", "core"]:
        if check_table_exists(conn, "target_breakdown", schema):
            found_schema = schema
            break
    
    if not found_schema:
        issues.append("[FAIL] target_breakdown 表不存在")
        recommendations.append("执行 Alembic 迁移: python -m alembic upgrade head")
        return issues, recommendations
    
    safe_print(f"[OK] target_breakdown 表存在 (schema: {found_schema})")
    
    # 检查数据
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {found_schema}.target_breakdown")
        count = cursor.fetchone()[0]
        safe_print(f"[INFO] target_breakdown 表当前有 {count} 条记录")
    except Exception as e:
        issues.append(f"[FAIL] 查询 target_breakdown 失败: {e}")
    finally:
        cursor.close()
    
    return issues, recommendations


def diagnose_platform_accounts(conn) -> tuple:
    """诊断 platform_accounts 表（用于目标管理的店铺列表）"""
    issues = []
    recommendations = []
    
    # 检查 core schema
    cursor = conn.cursor()
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.schemata 
            WHERE schema_name = 'core'
        )
    """)
    core_exists = cursor.fetchone()[0]
    cursor.close()
    
    if not core_exists:
        safe_print("[INFO] core schema 不存在，检查 public schema")
    
    # 检查 platform_accounts 表
    schema = "core" if core_exists else "public"
    if not check_table_exists(conn, "platform_accounts", schema):
        # 也检查 public schema
        if not check_table_exists(conn, "platform_accounts", "public"):
            issues.append("[WARN] platform_accounts 表不存在（店铺列表将为空）")
            recommendations.append("platform_accounts 表用于目标管理的店铺选择，请确保账号管理模块已初始化")
            return issues, recommendations
        schema = "public"
    
    safe_print(f"[OK] platform_accounts 表存在 (schema: {schema})")
    
    # 检查数据
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {schema}.platform_accounts WHERE enabled = true")
        count = cursor.fetchone()[0]
        safe_print(f"[INFO] platform_accounts 表当前有 {count} 条启用的账号")
        if count == 0:
            issues.append("[WARN] 无启用的账号，目标管理的店铺列表将为空")
            recommendations.append("请在账号管理中添加平台账号")
    except Exception as e:
        issues.append(f"[FAIL] 查询 platform_accounts 失败: {e}")
    finally:
        cursor.close()
    
    return issues, recommendations


def diagnose_a_class_tables(conn) -> tuple:
    """诊断 A 类数据表（a_class schema）"""
    issues = []
    recommendations = []
    
    # 检查 a_class schema
    cursor = conn.cursor()
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.schemata 
            WHERE schema_name = 'a_class'
        )
    """)
    a_class_exists = cursor.fetchone()[0]
    cursor.close()
    
    if not a_class_exists:
        issues.append("[WARN] a_class schema 不存在")
        recommendations.append("执行迁移以创建 a_class schema: python -m alembic upgrade head")
        return issues, recommendations
    
    safe_print("[OK] a_class schema 存在")
    
    # 检查 sales_targets_a 表
    if check_table_exists(conn, "sales_targets_a", "a_class"):
        safe_print("[OK] a_class.sales_targets_a 表存在")
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM a_class.sales_targets_a")
            count = cursor.fetchone()[0]
            safe_print(f"[INFO] a_class.sales_targets_a 表当前有 {count} 条记录")
        except Exception as e:
            issues.append(f"[FAIL] 查询 a_class.sales_targets_a 失败: {e}")
        finally:
            cursor.close()
    else:
        issues.append("[WARN] a_class.sales_targets_a 表不存在")
        recommendations.append("此表用于经营指标 Question，建议执行迁移创建")
    
    return issues, recommendations


def main():
    """主函数"""
    safe_print("=" * 60)
    safe_print("目标管理数据库诊断工具")
    safe_print("=" * 60)
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
        safe_print("")
    except Exception as e:
        safe_print(f"[FAIL] 数据库连接失败: {e}")
        safe_print("[提示] 请确保 PostgreSQL 正在运行，且 DATABASE_URL 配置正确")
        return 1
    
    all_issues = []
    all_recommendations = []
    
    # 1. 诊断 sales_targets 表
    safe_print("--- 检查 sales_targets 表 ---")
    issues, recommendations = diagnose_sales_targets(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recommendations)
    safe_print("")
    
    # 2. 诊断 target_breakdown 表
    safe_print("--- 检查 target_breakdown 表 ---")
    issues, recommendations = diagnose_target_breakdown(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recommendations)
    safe_print("")
    
    # 3. 诊断 platform_accounts 表
    safe_print("--- 检查 platform_accounts 表 ---")
    issues, recommendations = diagnose_platform_accounts(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recommendations)
    safe_print("")
    
    # 4. 诊断 A 类数据表
    safe_print("--- 检查 A 类数据表 ---")
    issues, recommendations = diagnose_a_class_tables(conn)
    all_issues.extend(issues)
    all_recommendations.extend(recommendations)
    safe_print("")
    
    conn.close()
    
    # 汇总
    safe_print("=" * 60)
    safe_print("诊断结果汇总")
    safe_print("=" * 60)
    
    fail_count = sum(1 for i in all_issues if "[FAIL]" in i)
    warn_count = sum(1 for i in all_issues if "[WARN]" in i)
    
    if fail_count == 0 and warn_count == 0:
        safe_print("[OK] 所有检查通过，数据库结构正常")
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
        for rec in all_recommendations:
            safe_print(f"  {rec}")
    
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
