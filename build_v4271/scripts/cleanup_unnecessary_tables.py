#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理不必要的表脚本

功能：
- 删除Superset系统表（21张）
- 删除重复的旧表（3张）
- 删除废弃表（1张）
- 删除Superset其他表（26张）

总计：51张表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import SessionLocal

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

# Superset系统表（21张）
SUPERSET_TABLES = [
    'ab_permission', 'ab_permission_view', 'ab_permission_view_role',
    'ab_register_user', 'ab_role', 'ab_user', 'ab_user_role',
    'ab_view_menu', 'annotation', 'annotation_layer', 'cache_keys',
    'css_templates', 'dashboard_roles', 'dashboard_slices',
    'dashboard_user', 'dashboards', 'logs', 'query', 'slices',
    'sql_metrics', 'table_columns'
]

# 重复的旧表（3张）
DUPLICATE_OLD_TABLES = [
    'dim_platform',  # 已有 dim_platforms
    'dim_shop',      # 已有 dim_shops
    'dim_product'    # 已有 dim_products
]

# 废弃表（1张）
DEPRECATED_TABLES = [
    'field_mappings_deprecated'
]

# Superset其他表（26张）
SUPERSET_OTHER_TABLES = [
    'sl_columns', 'sl_dataset_columns', 'sl_dataset_tables',
    'sl_dataset_users', 'sl_datasets', 'sl_table_columns',
    'sl_tables', 'slice_user', 'sqlatable_user', 'saved_query',
    'tables', 'tag', 'tagged_object', 'url', 'dbs',
    'embedded_dashboards', 'filter_sets', 'tab_state',
    'table_schema', 'user_attribute', 'ssh_tunnels',
    'row_level_security_filters', 'rls_filter_roles',
    'rls_filter_tables', 'dynamic_plugin', 'favstar'
]

# 所有可删除的表
ALL_DELETABLE_TABLES = (
    SUPERSET_TABLES +
    DUPLICATE_OLD_TABLES +
    DEPRECATED_TABLES +
    SUPERSET_OTHER_TABLES
)

def cleanup_unnecessary_tables(dry_run: bool = True):
    """清理不必要的表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        existing_tables = set(inspector.get_table_names(schema='public'))
        
        # 找出实际存在的可删除表
        tables_to_drop = []
        for table_name in ALL_DELETABLE_TABLES:
            if table_name in existing_tables:
                tables_to_drop.append(table_name)
        
        safe_print("="*80)
        safe_print("清理不必要的表")
        safe_print("="*80)
        safe_print(f"\n发现 {len(tables_to_drop)} 张可删除的表:")
        
        # 按类别显示
        categories = {
            'Superset系统表': [t for t in tables_to_drop if t in SUPERSET_TABLES],
            '重复的旧表': [t for t in tables_to_drop if t in DUPLICATE_OLD_TABLES],
            '废弃表': [t for t in tables_to_drop if t in DEPRECATED_TABLES],
            'Superset其他表': [t for t in tables_to_drop if t in SUPERSET_OTHER_TABLES]
        }
        
        for category, tables in categories.items():
            if tables:
                safe_print(f"\n[{category}] {len(tables)} 张:")
                for table in sorted(tables):
                    try:
                        count = db.execute(
                            text(f'SELECT COUNT(*) FROM "{table}"')
                        ).scalar() or 0
                        safe_print(f"  - {table}: {count} 行")
                    except:
                        safe_print(f"  - {table}: (视图或无法查询)")
        
        if not tables_to_drop:
            safe_print("\n[OK] 没有需要清理的表")
            return
        
        if dry_run:
            safe_print(f"\n[DRY RUN] 以上 {len(tables_to_drop)} 张表将被删除（实际未执行）")
            safe_print("[提示] 要实际删除，请使用: python scripts/cleanup_unnecessary_tables.py --execute")
            return
        
        # 实际删除
        safe_print(f"\n开始删除 {len(tables_to_drop)} 张表...")
        deleted_count = 0
        failed_count = 0
        
        for table_name in sorted(tables_to_drop):
            try:
                db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
                db.commit()
                safe_print(f"  [OK] 删除表: {table_name}")
                deleted_count += 1
            except Exception as e:
                db.rollback()
                safe_print(f"  [FAIL] 删除表失败: {table_name}, 错误: {e}")
                failed_count += 1
        
        safe_print(f"\n删除完成: 成功 {deleted_count} 张, 失败 {failed_count} 张")
        
        # 验证剩余表数
        remaining_tables = inspector.get_table_names(schema='public')
        safe_print(f"\n剩余表数: {len(remaining_tables)} 张")
        
    except Exception as e:
        safe_print(f"[ERROR] 清理过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="清理不必要的表脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除（默认只显示将要删除的表）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        safe_print("[DRY RUN] 运行模式: 只显示，不删除")
    else:
        safe_print("[EXECUTE] 运行模式: 将实际删除表")
        safe_print("[警告] 请确认这是开发环境，生产环境需要先备份！")
    
    cleanup_unnecessary_tables(dry_run=dry_run)

