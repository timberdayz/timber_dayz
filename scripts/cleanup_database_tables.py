#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表清理脚本（Database Table Cleanup）

功能：
1. 分析当前所有表，按schema分类
2. 识别废弃表、重复表、无用表
3. 提供清理方案（dry-run模式）
4. 实际执行清理（execute模式）

数据流转规则：
- a_class: 用户前端输入的数据（销售战役、目标管理、绩效配置等）
- b_class: 数据采集自动同步的数据（订单、产品、流量等）
- c_class: 计算输出的数据（员工绩效、佣金、评分等）
- core: 核心ERP表（系统必需的管理表和维度表）
- finance: 财务域表（采购、库存、发票等）
- public: 其他表（视图、物化视图等）

注意：
- 本脚本连接Docker PostgreSQL数据库
- 默认dry-run模式，只显示将要删除的表
- 使用--execute参数才会实际删除
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from collections import defaultdict

from backend.models.database import engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


# ==================== 表分类定义 ====================

# a_class Schema - 应该包含的表（用户输入数据）
A_CLASS_TABLES = {
    'sales_targets_a',           # 销售目标配置
    'sales_campaigns_a',         # 销售战役配置
    'operating_costs',           # 运营成本配置
    'employees',                 # 员工信息
    'employee_targets',          # 员工目标配置
    'attendance_records',        # 考勤记录
    'performance_config_a',      # 绩效配置
}

# b_class Schema - 应该包含的表（数据采集）
B_CLASS_TABLES = {
    # 按平台分表的订单数据（新架构）
    'fact_shopee_orders_daily',
    'fact_shopee_orders_weekly',
    'fact_shopee_orders_monthly',
    'fact_tiktok_orders_daily',
    'fact_tiktok_orders_weekly',
    'fact_tiktok_orders_monthly',
    # 产品数据
    'fact_raw_data_products_daily',
    'fact_raw_data_products_weekly',
    'fact_raw_data_products_monthly',
    # 分析数据（analytics，traffic已迁移）
    'fact_raw_data_analytics_daily',
    'fact_raw_data_analytics_weekly',
    'fact_raw_data_analytics_monthly',
    # 服务数据（按sub_domain分表）
    'fact_raw_data_services_ai_assistant_daily',
    'fact_raw_data_services_ai_assistant_weekly',
    'fact_raw_data_services_agent_daily',
    'fact_raw_data_services_agent_weekly',
    # 库存数据
    'fact_raw_data_inventory_snapshot',
    # 其他
    'entity_aliases',
    'staging_raw_data',
}

# c_class Schema - 应该包含的表（计算输出）
C_CLASS_TABLES = {
    'employee_performance',      # 员工绩效
    'employee_commissions',      # 员工佣金
    'shop_commissions',          # 店铺佣金
    'performance_scores_c',     # 绩效评分
}

# core Schema - 应该包含的表（核心ERP表）
CORE_TABLES = {
    'catalog_files',
    'data_files',
    'data_records',
    'field_mapping_templates',
    'field_mapping_template_items',
    'field_mapping_dictionary',
    'mapping_sessions',
    'dim_platforms',
    'dim_shops',
    'dim_products',
    'dim_product_master',
    'bridge_product_keys',
    'dim_currency_rates',
    'accounts',
    'collection_tasks',
    'data_quarantine',
    'staging_orders',
    'staging_product_metrics',
    'alembic_version',
}

# ==================== 废弃表清单 ====================

# 已废弃的表（应该删除）
DEPRECATED_TABLES = [
    # 旧事实表（已被fact_raw_data_*替代）
    'fact_orders',
    'fact_order_items',
    'fact_product_metrics',
    
    # traffic域表（已迁移到analytics）
    'fact_raw_data_traffic_daily',
    'fact_raw_data_traffic_weekly',
    'fact_raw_data_traffic_monthly',
    
    # services域旧表（已按sub_domain分表）
    'fact_raw_data_services_daily',
    'fact_raw_data_services_weekly',
    'fact_raw_data_services_monthly',
    
    # 旧的fact_raw_data_orders_*表（已按平台分表）
    'fact_raw_data_orders_daily',
    'fact_raw_data_orders_weekly',
    'fact_raw_data_orders_monthly',
]

# 重复的旧表（已有新版本）
DUPLICATE_TABLES = [
    'dim_platform',      # 已有 dim_platforms
    'dim_shop',          # 已有 dim_shops
    'dim_product',       # 已有 dim_products
]

# Superset系统表（如果存在）
SUPERSET_TABLES = [
    'ab_permission', 'ab_permission_view', 'ab_permission_view_role',
    'ab_register_user', 'ab_role', 'ab_user', 'ab_user_role',
    'ab_view_menu', 'annotation', 'annotation_layer', 'cache_keys',
    'css_templates', 'dashboard_roles', 'dashboard_slices',
    'dashboard_user', 'dashboards', 'logs', 'query', 'slices',
    'sql_metrics', 'table_columns',
    'sl_columns', 'sl_dataset_columns', 'sl_dataset_tables',
    'sl_dataset_users', 'sl_datasets', 'sl_table_columns',
    'sl_tables', 'slice_user', 'sqlatable_user', 'saved_query',
    'tables', 'tag', 'tagged_object', 'url', 'dbs',
    'embedded_dashboards', 'filter_sets', 'tab_state',
    'table_schema', 'user_attribute', 'ssh_tunnels',
    'row_level_security_filters', 'rls_filter_roles',
    'rls_filter_tables', 'dynamic_plugin', 'favstar',
]

# 所有可删除的表
ALL_DELETABLE_TABLES = (
    DEPRECATED_TABLES +
    DUPLICATE_TABLES +
    SUPERSET_TABLES
)


# ==================== 清理函数 ====================

def safe_print(text):
    """安全打印（处理Windows编码问题）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def analyze_tables_by_schema():
    """
    分析所有表，按schema分类
    
    Returns:
        dict: {schema_name: [table_names]}
    """
    inspector = inspect(engine)
    
    # 获取所有schema
    schemas = inspector.get_schema_names()
    
    # 按schema分类表
    tables_by_schema = defaultdict(list)
    
    for schema in schemas:
        # 跳过系统schema
        if schema in ('information_schema', 'pg_catalog', 'pg_toast'):
            continue
        
        try:
            tables = inspector.get_table_names(schema=schema)
            if tables:
                tables_by_schema[schema] = tables
        except Exception as e:
            logger.warning(f"无法获取schema {schema}的表: {e}")
    
    return dict(tables_by_schema)


def find_tables_to_cleanup(tables_by_schema):
    """
    找出需要清理的表
    
    Returns:
        dict: {
            'deprecated': [...],
            'duplicate': [...],
            'superset': [...],
            'orphaned': [...],  # 不在任何分类中的表
        }
    """
    all_tables = []
    for schema, tables in tables_by_schema.items():
        for table in tables:
            if schema == 'public':
                all_tables.append(table)
            else:
                all_tables.append(f"{schema}.{table}")
    
    # 找出废弃表
    deprecated = []
    duplicate = []
    superset = []
    orphaned = []
    
    for table_full_name in all_tables:
        # 提取表名（去掉schema前缀）
        table_name = table_full_name.split('.')[-1]
        
        if table_name in DEPRECATED_TABLES:
            deprecated.append(table_full_name)
        elif table_name in DUPLICATE_TABLES:
            duplicate.append(table_full_name)
        elif table_name in SUPERSET_TABLES:
            superset.append(table_full_name)
        elif table_name not in (
            A_CLASS_TABLES | B_CLASS_TABLES | C_CLASS_TABLES | CORE_TABLES
        ):
            # 检查是否是物化视图或其他系统表
            if not table_name.startswith('mv_') and not table_name.startswith('pg_'):
                # 检查是否是alembic版本表
                if table_name != 'alembic_version':
                    orphaned.append(table_full_name)
    
    return {
        'deprecated': deprecated,
        'duplicate': duplicate,
        'superset': superset,
        'orphaned': orphaned,
    }


def print_analysis_report(tables_by_schema, tables_to_cleanup):
    """
    打印分析报告
    """
    safe_print("=" * 80)
    safe_print("数据库表分析报告")
    safe_print("=" * 80)
    
    # 按schema显示表
    safe_print("\n[Schema分类]")
    for schema, tables in sorted(tables_by_schema.items()):
        safe_print(f"  {schema}: {len(tables)} 张表")
        for table in sorted(tables):
            safe_print(f"    - {table}")
    
    # 显示需要清理的表
    safe_print("\n[需要清理的表]")
    total_to_cleanup = sum(len(tables) for tables in tables_to_cleanup.values())
    safe_print(f"  总计: {total_to_cleanup} 张表")
    
    if tables_to_cleanup['deprecated']:
        safe_print(f"\n  废弃表: {len(tables_to_cleanup['deprecated'])} 张")
        for table in sorted(tables_to_cleanup['deprecated']):
            safe_print(f"    - {table}")
    
    if tables_to_cleanup['duplicate']:
        safe_print(f"\n  重复表: {len(tables_to_cleanup['duplicate'])} 张")
        for table in sorted(tables_to_cleanup['duplicate']):
            safe_print(f"    - {table}")
    
    if tables_to_cleanup['superset']:
        safe_print(f"\n  Superset表: {len(tables_to_cleanup['superset'])} 张")
        for table in sorted(tables_to_cleanup['superset']):
            safe_print(f"    - {table}")
    
    if tables_to_cleanup['orphaned']:
        safe_print(f"\n  孤立表: {len(tables_to_cleanup['orphaned'])} 张（需要人工确认）")
        for table in sorted(tables_to_cleanup['orphaned']):
            safe_print(f"    - {table}")
    
    safe_print("=" * 80)


def cleanup_tables(tables_to_cleanup, dry_run=True):
    """
    清理表
    
    Args:
        tables_to_cleanup: 需要清理的表列表
        dry_run: 如果为True，只显示将要删除的表，不实际删除
    """
    if not tables_to_cleanup:
        safe_print("[Cleanup] 没有需要清理的表")
        return
    
    session = Session(engine)
    
    try:
        if dry_run:
            safe_print(f"[Cleanup] [DRY RUN] 以下 {len(tables_to_cleanup)} 个表将被删除（实际未执行）:")
            for table_full_name in sorted(tables_to_cleanup):
                safe_print(f"  - {table_full_name}")
            return
        
        # 实际删除
        safe_print(f"[Cleanup] 开始删除 {len(tables_to_cleanup)} 个表...")
        success_count = 0
        fail_count = 0
        
        for table_full_name in sorted(tables_to_cleanup):
            try:
                # 解析schema和表名
                if '.' in table_full_name:
                    schema, table_name = table_full_name.split('.', 1)
                    drop_sql = text(f'DROP TABLE IF EXISTS "{schema}"."{table_name}" CASCADE')
                else:
                    table_name = table_full_name
                    drop_sql = text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
                
                session.execute(drop_sql)
                session.commit()
                safe_print(f"[Cleanup] [OK] 成功删除: {table_full_name}")
                success_count += 1
            except Exception as e:
                session.rollback()
                safe_print(f"[Cleanup] [FAIL] 删除失败: {table_full_name}, 错误: {e}")
                fail_count += 1
        
        safe_print(f"[Cleanup] 清理完成: 成功 {success_count} 个, 失败 {fail_count} 个")
        
    except Exception as e:
        session.rollback()
        logger.error(f"[Cleanup] 清理过程出错: {e}", exc_info=True)
        safe_print(f"[Cleanup] [ERROR] 清理过程出错: {e}")
        raise
    finally:
        session.close()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库表清理脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除（默认只显示将要删除的表）"
    )
    
    args = parser.parse_args()
    dry_run = not args.execute
    
    try:
        # 1. 分析所有表
        safe_print("\n[分析] 正在分析数据库表...")
        tables_by_schema = analyze_tables_by_schema()
        
        # 2. 找出需要清理的表
        safe_print("[分析] 正在识别需要清理的表...")
        tables_to_cleanup = find_tables_to_cleanup(tables_by_schema)
        
        # 3. 打印分析报告
        print_analysis_report(tables_by_schema, tables_to_cleanup)
        
        # 4. 准备清理列表（只清理废弃表、重复表、Superset表，不包括孤立表）
        all_tables_to_cleanup = (
            tables_to_cleanup['deprecated'] +
            tables_to_cleanup['duplicate'] +
            tables_to_cleanup['superset']
        )
        
        # 5. 执行清理
        if all_tables_to_cleanup:
            cleanup_tables(all_tables_to_cleanup, dry_run=dry_run)
        else:
            safe_print("\n[总结] 没有发现需要清理的表")
            
    except Exception as e:
        logger.error(f"分析过程出错: {e}", exc_info=True)
        safe_print(f"\n[错误] 分析失败: {e}")
        raise


if __name__ == "__main__":
    main()

