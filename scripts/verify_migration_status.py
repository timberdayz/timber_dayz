#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证迁移状态脚本

检查：
1. Alembic 当前版本
2. fact_orders 和 fact_order_items 表是否存在
3. A/C 类表是否在正确的 schema 中
4. public schema 中是否有重复表
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(msg):
    """Safe print for Windows GBK encoding"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def check_alembic_version():
    """检查 Alembic 版本"""
    safe_print("\n" + "="*60)
    safe_print("1. 检查 Alembic 版本")
    safe_print("="*60)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            safe_print(f"[OK] 当前 Alembic 版本: {version}")
            return version
    except Exception as e:
        safe_print(f"[ERROR] 无法读取 Alembic 版本: {e}")
        return None


def check_fact_orders_tables():
    """检查 fact_orders 和 fact_order_items 表"""
    safe_print("\n" + "="*60)
    safe_print("2. 检查 fact_orders 和 fact_order_items 表")
    safe_print("="*60)
    
    inspector = inspect(engine)
    results = {}
    
    # 检查所有 schema 中的表
    schemas = ['public', 'a_class', 'b_class', 'c_class', 'core']
    
    for schema in schemas:
        try:
            tables = inspector.get_table_names(schema=schema)
            if 'fact_orders' in tables:
                results['fact_orders'] = schema
                safe_print(f"[WARN] fact_orders 存在于 {schema} schema")
            if 'fact_order_items' in tables:
                results['fact_order_items'] = schema
                safe_print(f"[WARN] fact_order_items 存在于 {schema} schema")
        except Exception as e:
            # schema 可能不存在，忽略
            pass
    
    if not results:
        safe_print("[OK] fact_orders 和 fact_order_items 表不存在（符合预期）")
    else:
        safe_print(f"[INFO] 发现表: {results}")
    
    return results


def check_a_class_tables():
    """检查 A 类表是否在正确的 schema"""
    safe_print("\n" + "="*60)
    safe_print("3. 检查 A 类表位置")
    safe_print("="*60)
    
    a_class_tables = [
        'sales_targets_a',
        'sales_campaigns_a',
        'operating_costs',
        'employees',
        'employee_targets',
        'attendance_records',
        'performance_config_a',
    ]
    
    inspector = inspect(engine)
    issues = []
    
    for table_name in a_class_tables:
        # 检查 a_class schema
        a_class_exists = False
        try:
            tables = inspector.get_table_names(schema='a_class')
            if table_name in tables:
                a_class_exists = True
        except:
            pass
        
        # 检查 public schema
        public_exists = False
        try:
            tables = inspector.get_table_names(schema='public')
            if table_name in tables:
                public_exists = True
        except:
            pass
        
        if a_class_exists and not public_exists:
            safe_print(f"[OK] {table_name} 在 a_class schema（正确）")
        elif public_exists and not a_class_exists:
            safe_print(f"[ERROR] {table_name} 在 public schema，但不在 a_class（需要迁移）")
            issues.append(table_name)
        elif public_exists and a_class_exists:
            safe_print(f"[WARN] {table_name} 同时存在于 public 和 a_class（重复表）")
            issues.append(table_name)
        else:
            safe_print(f"[INFO] {table_name} 不存在（可能未创建）")
    
    return issues


def check_c_class_tables():
    """检查 C 类表是否在正确的 schema"""
    safe_print("\n" + "="*60)
    safe_print("4. 检查 C 类表位置")
    safe_print("="*60)
    
    c_class_tables = [
        'employee_performance',
        'employee_commissions',
        'shop_commissions',
        'performance_scores_c',
    ]
    
    inspector = inspect(engine)
    issues = []
    
    for table_name in c_class_tables:
        # 检查 c_class schema
        c_class_exists = False
        try:
            tables = inspector.get_table_names(schema='c_class')
            if table_name in tables:
                c_class_exists = True
        except:
            pass
        
        # 检查 public schema
        public_exists = False
        try:
            tables = inspector.get_table_names(schema='public')
            if table_name in tables:
                public_exists = True
        except:
            pass
        
        if c_class_exists and not public_exists:
            safe_print(f"[OK] {table_name} 在 c_class schema（正确）")
        elif public_exists and not c_class_exists:
            safe_print(f"[ERROR] {table_name} 在 public schema，但不在 c_class（需要迁移）")
            issues.append(table_name)
        elif public_exists and c_class_exists:
            safe_print(f"[WARN] {table_name} 同时存在于 public 和 c_class（重复表）")
            issues.append(table_name)
        else:
            safe_print(f"[INFO] {table_name} 不存在（可能未创建）")
    
    return issues


def check_public_schema_tables():
    """检查 public schema 中的表统计"""
    safe_print("\n" + "="*60)
    safe_print("5. public schema 表统计")
    safe_print("="*60)
    
    inspector = inspect(engine)
    try:
        tables = inspector.get_table_names(schema='public')
        safe_print(f"[INFO] public schema 中共有 {len(tables)} 张表")
        
        # 列出所有 fact_* 表
        fact_tables = [t for t in tables if t.startswith('fact_')]
        if fact_tables:
            safe_print(f"[INFO] public schema 中的 fact_* 表 ({len(fact_tables)} 张):")
            for table in sorted(fact_tables):
                safe_print(f"  - {table}")
    except Exception as e:
        safe_print(f"[ERROR] 无法获取 public schema 表列表: {e}")


def main():
    """主函数"""
    safe_print("\n" + "="*60)
    safe_print("数据库迁移状态验证")
    safe_print("="*60)
    
    # 1. 检查 Alembic 版本
    alembic_version = check_alembic_version()
    
    # 2. 检查 fact_orders 表
    fact_tables = check_fact_orders_tables()
    
    # 3. 检查 A 类表
    a_class_issues = check_a_class_tables()
    
    # 4. 检查 C 类表
    c_class_issues = check_c_class_tables()
    
    # 5. 统计 public schema
    check_public_schema_tables()
    
    # 总结
    safe_print("\n" + "="*60)
    safe_print("验证总结")
    safe_print("="*60)
    
    if alembic_version:
        safe_print(f"✓ Alembic 版本: {alembic_version}")
    
    if fact_tables:
        safe_print(f"⚠ fact_orders/fact_order_items 仍存在: {fact_tables}")
        safe_print("  建议: 如果这些表已废弃，可以手动删除")
    else:
        safe_print("✓ fact_orders/fact_order_items 已删除（符合预期）")
    
    if a_class_issues:
        safe_print(f"⚠ A 类表问题: {len(a_class_issues)} 张表需要处理")
        for issue in a_class_issues:
            safe_print(f"  - {issue}")
    else:
        safe_print("✓ A 类表位置正确")
    
    if c_class_issues:
        safe_print(f"⚠ C 类表问题: {len(c_class_issues)} 张表需要处理")
        for issue in c_class_issues:
            safe_print(f"  - {issue}")
    else:
        safe_print("✓ C 类表位置正确")
    
    safe_print("\n验证完成！")


if __name__ == "__main__":
    main()
