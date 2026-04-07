#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析表清理计划

根据审计结果，识别：
1. 真正的历史遗留表（可以安全清理）
2. 动态创建的表（需要保留，如fact_shopee_*）
3. 需要补充迁移的表（schema.py中定义但无迁移记录）
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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


def main():
    safe_print("=" * 80)
    safe_print("表清理计划分析")
    safe_print("=" * 80)
    
    # 从审计报告中提取的历史遗留表（不在schema.py中，也不在迁移中）
    legacy_tables_from_audit = {
        # a_class schema
        'campaign_targets',
        
        # b_class schema（动态创建的表，需要保留）
        'fact_miaoshou_inventory_snapshot',
        'fact_shopee_analytics_daily',
        'fact_shopee_analytics_monthly',
        'fact_shopee_analytics_weekly',
        'fact_shopee_orders_monthly',
        'fact_shopee_orders_weekly',
        'fact_shopee_products_daily',
        'fact_shopee_products_monthly',
        'fact_shopee_products_weekly',
        'fact_shopee_services_agent_daily',
        'fact_shopee_services_agent_monthly',
        'fact_shopee_services_agent_weekly',
        'fact_shopee_services_ai_assistant_daily',
        'fact_shopee_services_ai_assistant_monthly',
        'fact_shopee_services_ai_assistant_weekly',
        'fact_test_platform_orders_daily',
        'fact_tiktok_analytics_daily',
        'fact_tiktok_analytics_monthly',
        'fact_tiktok_analytics_weekly',
        'fact_tiktok_orders_monthly',
        'fact_tiktok_orders_weekly',
        'fact_tiktok_products_daily',
        'fact_tiktok_products_monthly',
        'fact_tiktok_products_weekly',
        'fact_tiktok_services_agent_daily',
        'fact_tiktok_services_agent_monthly',
        
        # core schema
        'dim_date',
        'fact_sales_orders',
        
        # public schema
        'collection_tasks_backup',
        'key_value',
        'keyvalue',
        'raw_ingestions',
        'report_execution_log',
        'report_recipient',
        'report_schedule',
        'report_schedule_user',
        'user_roles',
    }
    
    # schema.py中定义的表
    schema_tables = set(Base.metadata.tables.keys())
    
    # 分类分析
    safe_print("\n[分类分析]")
    
    # 1. 动态创建的表（b_class schema中的fact_*表）- 需要保留
    dynamic_b_class_tables = {
        t for t in legacy_tables_from_audit 
        if t.startswith('fact_') and ('shopee' in t or 'tiktok' in t or 'miaoshou' in t or 'test' in t)
    }
    safe_print(f"\n1. 动态创建的表（b_class schema，需要保留）: {len(dynamic_b_class_tables)} 张")
    safe_print("   说明: 这些表通过PlatformTableManager动态创建，不在schema.py中定义")
    safe_print("   操作: 保留，不需要迁移")
    for table in sorted(dynamic_b_class_tables):
        safe_print(f"     - {table}")
    
    # 2. 真正的历史遗留表（可以清理）
    real_legacy_tables = legacy_tables_from_audit - dynamic_b_class_tables
    safe_print(f"\n2. 真正的历史遗留表（可以清理）: {len(real_legacy_tables)} 张")
    
    # 按schema分类
    legacy_by_schema = {
        'a_class': [],
        'core': [],
        'public': [],
    }
    
    for table in real_legacy_tables:
        if table == 'campaign_targets':
            legacy_by_schema['a_class'].append(table)
        elif table in ['dim_date', 'fact_sales_orders']:
            legacy_by_schema['core'].append(table)
        else:
            legacy_by_schema['public'].append(table)
    
    for schema, tables in legacy_by_schema.items():
        if tables:
            safe_print(f"\n   [{schema}] schema ({len(tables)} 张):")
            for table in sorted(tables):
                safe_print(f"     - {table}")
    
    # 3. 检查这些表是否在schema.py中（不应该在）
    safe_print("\n3. 检查遗留表是否在schema.py中定义...")
    legacy_in_schema = real_legacy_tables & schema_tables
    if legacy_in_schema:
        safe_print(f"   [WARNING] 以下表在schema.py中定义，但被标记为遗留表: {len(legacy_in_schema)} 张")
        for table in sorted(legacy_in_schema):
            safe_print(f"     - {table}")
    else:
        safe_print("   [OK] 所有遗留表都不在schema.py中定义（正确）")
    
    # 4. 清理建议
    safe_print("\n" + "=" * 80)
    safe_print("清理建议")
    safe_print("=" * 80)
    
    safe_print("\n[可以安全清理的表]")
    for schema, tables in legacy_by_schema.items():
        if tables:
            safe_print(f"\n{schema} schema:")
            for table in sorted(tables):
                safe_print(f"  - {table}")
                # 提供清理SQL
                if schema == 'public':
                    safe_print(f"    DROP TABLE IF EXISTS {table} CASCADE;")
                else:
                    safe_print(f"    DROP TABLE IF EXISTS {schema}.{table} CASCADE;")
    
    safe_print("\n[需要保留的表（动态创建）]")
    safe_print("b_class schema中的fact_*表（通过PlatformTableManager动态创建）")
    safe_print("操作: 不需要清理，不需要迁移，正常使用")
    
    safe_print("\n[建议清理步骤]")
    safe_print("1. 备份数据库（重要！）")
    safe_print("2. 检查这些表是否有数据（如果有重要数据，需要迁移）")
    safe_print("3. 确认这些表未被代码引用（grep搜索表名）")
    safe_print("4. 执行清理SQL（谨慎操作）")
    safe_print("5. 更新审计报告")
    
    safe_print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
