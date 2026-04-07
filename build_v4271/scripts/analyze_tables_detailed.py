#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细分析表，识别重复、废弃和可删除的表
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

def analyze_tables_detailed():
    """详细分析表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        all_tables = inspector.get_table_names(schema='public')
        
        safe_print("="*80)
        safe_print("详细表分析 - 识别重复、废弃和可删除的表")
        safe_print("="*80)
        
        # 1. 识别重复表（旧版本vs新版本）
        safe_print("\n" + "="*80)
        safe_print("1. 重复表分析（旧版本 vs 新版本）")
        safe_print("="*80)
        
        duplicate_pairs = [
            ('dim_platform', 'dim_platforms'),
            ('dim_shop', 'dim_shops'),
            ('dim_product', 'dim_products'),
        ]
        
        duplicates = []
        for old_table, new_table in duplicate_pairs:
            if old_table in all_tables and new_table in all_tables:
                try:
                    old_count = db.execute(text(f'SELECT COUNT(*) FROM "{old_table}"')).scalar() or 0
                    new_count = db.execute(text(f'SELECT COUNT(*) FROM "{new_table}"')).scalar() or 0
                    duplicates.append({
                        'old': old_table,
                        'new': new_table,
                        'old_count': old_count,
                        'new_count': new_count
                    })
                    safe_print(f"  [重复] {old_table} ({old_count}行) vs {new_table} ({new_count}行)")
                except:
                    pass
        
        # 2. 识别废弃表
        safe_print("\n" + "="*80)
        safe_print("2. 废弃表分析")
        safe_print("="*80)
        
        deprecated_tables = [
            'field_mappings_deprecated',  # 已废弃的字段映射表
        ]
        
        for table in deprecated_tables:
            if table in all_tables:
                try:
                    count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
                    safe_print(f"  [废弃] {table}: {count} 行")
                except:
                    safe_print(f"  [废弃] {table}: (无法查询)")
        
        # 3. 识别Superset相关表（在OTHER分类中）
        safe_print("\n" + "="*80)
        safe_print("3. Superset相关表（OTHER分类中）")
        safe_print("="*80)
        
        superset_other = [
            'sl_columns', 'sl_dataset_columns', 'sl_dataset_tables',
            'sl_dataset_users', 'sl_datasets', 'sl_table_columns',
            'sl_tables', 'slice_user', 'sqlatable_user', 'saved_query',
            'tables', 'tag', 'tagged_object', 'url', 'dbs',
            'embedded_dashboards', 'filter_sets', 'tab_state',
            'table_schema', 'user_attribute', 'ssh_tunnels',
            'row_level_security_filters', 'rls_filter_roles',
            'rls_filter_tables', 'dynamic_plugin', 'favstar'
        ]
        
        found_superset = []
        for table in superset_other:
            if table in all_tables:
                try:
                    count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
                    found_superset.append(table)
                    safe_print(f"  [Superset] {table}: {count} 行")
                except:
                    pass
        
        # 4. 识别空表（0行，可能不需要）
        safe_print("\n" + "="*80)
        safe_print("4. 空表分析（0行，可能不需要）")
        safe_print("="*80)
        
        empty_tables = []
        for table in sorted(all_tables):
            # 跳过已知必需的空表
            if table in ['alembic_version', 'data_quarantine']:
                continue
            try:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
                if count == 0:
                    empty_tables.append(table)
            except:
                pass
        
        safe_print(f"\n发现 {len(empty_tables)} 张空表（0行）")
        safe_print("前30张空表:")
        for table in empty_tables[:30]:
            safe_print(f"  - {table}")
        if len(empty_tables) > 30:
            safe_print(f"  ... 还有 {len(empty_tables) - 30} 张空表")
        
        # 5. 总结和建议
        safe_print("\n" + "="*80)
        safe_print("5. 清理建议总结")
        safe_print("="*80)
        
        # 可删除的表
        deletable_tables = []
        
        # 重复的旧表
        for dup in duplicates:
            if dup['old_count'] == 0:  # 旧表为空
                deletable_tables.append(dup['old'])
        
        # 废弃表
        deletable_tables.extend(deprecated_tables)
        
        # Superset表（OTHER分类中）
        deletable_tables.extend(found_superset)
        
        safe_print(f"\n可删除的表（{len(deletable_tables)} 张）:")
        for table in sorted(deletable_tables):
            safe_print(f"  - {table}")
        
        safe_print(f"\n建议:")
        safe_print(f"  1. 删除重复的旧表: {len(duplicates)} 对")
        safe_print(f"  2. 删除废弃表: {len(deprecated_tables)} 张")
        safe_print(f"  3. 删除Superset表（OTHER分类）: {len(found_superset)} 张")
        safe_print(f"  4. 删除后预计减少: {len(deletable_tables)} 张表")
        safe_print(f"  5. 删除后预计表数: {len(all_tables) - len(deletable_tables)} 张")
        
        # 保存可删除表列表
        output_file = Path(__file__).parent.parent / "temp" / "development" / "deletable_tables.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("可删除的表列表\n")
            f.write("="*80 + "\n\n")
            for table in sorted(deletable_tables):
                f.write(f"{table}\n")
        
        safe_print(f"\n可删除表列表已保存到: {output_file}")
        
    except Exception as e:
        safe_print(f"[ERROR] 分析过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    analyze_tables_detailed()

