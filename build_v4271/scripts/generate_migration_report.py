#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成迁移验证报告
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import engine

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)

def main():
    safe_print("\n" + "="*80)
    safe_print("数据库迁移验证报告")
    safe_print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print("="*80)
    
    inspector = inspect(engine)
    
    # 1. Alembic 版本检查
    safe_print("\n【1. Alembic 版本状态】")
    safe_print("-" * 80)
    
    versions = {}
    schemas = ['public', 'core', 'a_class', 'b_class', 'c_class']
    for schema in schemas:
        try:
            tables = inspector.get_table_names(schema=schema)
            if 'alembic_version' in tables:
                with engine.connect() as conn:
                    result = conn.execute(text(f'SELECT version_num FROM "{schema}".alembic_version'))
                    version = result.scalar()
                    versions[schema] = version
                    safe_print(f"  {schema}.alembic_version = {version}")
        except:
            pass
    
    if 'core' in versions and versions['core'] == 'migrate_a_c_class_to_schema':
        safe_print("\n  ✓ Alembic 迁移已执行到最新版本")
    else:
        safe_print("\n  ⚠ Alembic 版本可能未更新")
    
    # 2. fact_orders 表检查
    safe_print("\n【2. fact_orders 和 fact_order_items 表状态】")
    safe_print("-" * 80)
    
    fact_tables_status = {}
    for table_name in ['fact_orders', 'fact_order_items']:
        for schema in schemas:
            try:
                tables = inspector.get_table_names(schema=schema)
                if table_name in tables:
                    with engine.connect() as conn:
                        result = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'))
                        count = result.scalar()
                        fact_tables_status[table_name] = {'schema': schema, 'count': count}
                        safe_print(f"  {schema}.{table_name}: {count} 行数据")
            except:
                pass
    
    if fact_tables_status:
        safe_print("\n  ⚠ 这些表仍然存在（根据迁移 20260127_rm_fact_orders，应该已删除）")
        safe_print("  建议: 如果确认已废弃，可以手动删除")
        safe_print("  命令: python scripts/fix_fact_orders_tables.py")
    else:
        safe_print("\n  ✓ fact_orders 和 fact_order_items 已删除（符合预期）")
    
    # 3. A 类表位置检查
    safe_print("\n【3. A 类表位置验证】")
    safe_print("-" * 80)
    
    a_class_tables = [
        'sales_targets', 'sales_targets_a', 'sales_campaigns_a', 'operating_costs',
        'employees', 'employee_targets', 'attendance_records', 'performance_config_a'
    ]
    
    a_class_ok = 0
    a_class_issues = []
    
    for table_name in a_class_tables:
        a_exists = False
        p_exists = False
        
        try:
            tables = inspector.get_table_names(schema='a_class')
            if table_name in tables:
                a_exists = True
        except:
            pass
        
        try:
            tables = inspector.get_table_names(schema='public')
            if table_name in tables:
                p_exists = True
        except:
            pass
        
        if a_exists and not p_exists:
            a_class_ok += 1
        elif p_exists:
            a_class_issues.append(table_name)
    
    safe_print(f"  ✓ 正确位置: {a_class_ok}/{len(a_class_tables)}")
    if a_class_issues:
        safe_print(f"  ⚠ 需要处理: {a_class_issues}")
    else:
        safe_print("  ✓ 所有 A 类表都在正确位置")
    
    # 4. C 类表位置检查
    safe_print("\n【4. C 类表位置验证】")
    safe_print("-" * 80)
    
    c_class_tables = [
        'employee_performance', 'employee_commissions',
        'shop_commissions', 'performance_scores', 'shop_health_scores', 'shop_alerts'
    ]
    
    c_class_ok = 0
    c_class_issues = []
    
    for table_name in c_class_tables:
        c_exists = False
        p_exists = False
        
        try:
            tables = inspector.get_table_names(schema='c_class')
            if table_name in tables:
                c_exists = True
        except:
            pass
        
        try:
            tables = inspector.get_table_names(schema='public')
            if table_name in tables:
                p_exists = True
        except:
            pass
        
        if c_exists and not p_exists:
            c_class_ok += 1
        elif p_exists:
            c_class_issues.append(table_name)
    
    safe_print(f"  ✓ 正确位置: {c_class_ok}/{len(c_class_tables)}")
    if c_class_issues:
        safe_print(f"  ⚠ 需要处理: {c_class_issues}")
    else:
        safe_print("  ✓ 所有 C 类表都在正确位置")
    
    # 5. 总结
    safe_print("\n" + "="*80)
    safe_print("【验证总结】")
    safe_print("="*80)
    
    issues_count = len(fact_tables_status) + len(a_class_issues) + len(c_class_issues)
    
    if issues_count == 0:
        safe_print("✓ 所有验证通过！数据库迁移状态正常。")
    else:
        safe_print(f"⚠ 发现 {issues_count} 个问题需要处理：")
        if fact_tables_status:
            safe_print(f"  - fact_orders/fact_order_items 表仍存在 ({len(fact_tables_status)} 张)")
        if a_class_issues:
            safe_print(f"  - A 类表位置问题 ({len(a_class_issues)} 张)")
        if c_class_issues:
            safe_print(f"  - C 类表位置问题 ({len(c_class_issues)} 张)")
        
        safe_print("\n建议操作：")
        if fact_tables_status:
            safe_print("  1. 运行: python scripts/fix_fact_orders_tables.py")
            safe_print("     这将检查并删除废弃的 fact_orders 和 fact_order_items 表")
    
    safe_print("\n报告生成完成！")

if __name__ == "__main__":
    main()
