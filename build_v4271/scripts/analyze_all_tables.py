#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析public schema中的所有表

功能：
- 列出所有表并分类
- 识别Superset系统表（可删除）
- 识别项目必需表
- 识别其他表（需要确认）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import SessionLocal
from collections import defaultdict

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def analyze_all_tables():
    """分析所有表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        
        # 获取所有表
        all_tables = inspector.get_table_names(schema='public')
        safe_print("="*80)
        safe_print(f"Public Schema表分析（共 {len(all_tables)} 张表）")
        safe_print("="*80)
        
        # 分类
        categories = {
            'superset': [],      # Superset系统表（可删除）
            'project_core': [],  # 项目核心表（必需）
            'finance': [],       # 财务域表
            'views': [],         # 视图
            'other': []           # 其他表
        }
        
        # Superset表前缀
        superset_prefixes = [
            'ab_', 'dashboards', 'slices', 'query', 'table_columns',
            'sql_metrics', 'datasources', 'logs', 'metrics', 'columns',
            'css_templates', 'dashboard_', 'annotation', 'cache_keys'
        ]
        
        # 项目核心表（从schema.py中提取）
        project_core_tables = [
            'catalog_files', 'accounts', 'dim_platforms', 'dim_shops', 
            'dim_products', 'fact_orders', 'fact_order_items', 
            'fact_product_metrics', 'field_mapping_', 'data_quarantine',
            'collection_tasks', 'sales_targets', 'target_breakdown',
            'staging_', 'alembic_version', 'dim_metric_formulas',
            'data_files', 'data_records', 'mapping_sessions',
            'entity_aliases', 'shop_health_score', 'sync_progress_tasks'
        ]
        
        # 财务域表前缀
        finance_prefixes = [
            'po_', 'grn_', 'invoice_', 'fact_expenses', 'inventory_ledger',
            'gl_', 'journal_', 'tax_', 'payment_', 'fact_inventory',
            'fact_order_amounts', 'fact_sales_orders'
        ]
        
        # 分类所有表
        for table in sorted(all_tables):
            categorized = False
            
            # 检查Superset表
            for prefix in superset_prefixes:
                if table.startswith(prefix):
                    categories['superset'].append(table)
                    categorized = True
                    break
            
            if categorized:
                continue
            
            # 检查项目核心表
            for prefix in project_core_tables:
                if table.startswith(prefix) or prefix in table:
                    categories['project_core'].append(table)
                    categorized = True
                    break
            
            if categorized:
                continue
            
            # 检查财务域表
            for prefix in finance_prefixes:
                if table.startswith(prefix):
                    categories['finance'].append(table)
                    categorized = True
                    break
            
            if categorized:
                continue
            
            # 检查视图
            if table.startswith('view_') or table.startswith('mv_'):
                categories['views'].append(table)
                continue
            
            # 其他表
            categories['other'].append(table)
        
        # 显示分类结果
        safe_print("\n" + "="*80)
        safe_print("表分类统计")
        safe_print("="*80)
        
        for category, tables in categories.items():
            safe_print(f"\n[{category.upper()}] {len(tables)} 张表:")
            if tables:
                for table in tables[:30]:  # 显示前30个
                    try:
                        count = db.execute(
                            text(f'SELECT COUNT(*) FROM "{table}"')
                        ).scalar() or 0
                        size_query = text(f"""
                            SELECT pg_size_pretty(pg_total_relation_size('"{table}"'))
                        """)
                        try:
                            size = db.execute(size_query).scalar() or "未知"
                            safe_print(f"  - {table}: {count} 行, {size}")
                        except:
                            safe_print(f"  - {table}: {count} 行")
                    except Exception as e:
                        if "is a view" in str(e).lower() or "does not exist" in str(e).lower():
                            safe_print(f"  - {table}: (视图)")
                        else:
                            safe_print(f"  - {table}: (查询失败: {str(e)[:50]})")
                if len(tables) > 30:
                    safe_print(f"  ... 还有 {len(tables) - 30} 张表")
        
        # 总结
        safe_print("\n" + "="*80)
        safe_print("总结和建议")
        safe_print("="*80)
        
        total = len(all_tables)
        superset_count = len(categories['superset'])
        project_count = len(categories['project_core'])
        finance_count = len(categories['finance'])
        views_count = len(categories['views'])
        other_count = len(categories['other'])
        
        safe_print(f"\n总表数: {total}")
        safe_print(f"  - Superset系统表: {superset_count} 张（可删除）")
        safe_print(f"  - 项目核心表: {project_count} 张（必需）")
        safe_print(f"  - 财务域表: {finance_count} 张（业务需要）")
        safe_print(f"  - 视图: {views_count} 张（查询优化）")
        safe_print(f"  - 其他表: {other_count} 张（需要确认）")
        
        safe_print(f"\n建议:")
        if superset_count > 0:
            safe_print(f"  1. 如果不再使用Superset，可以删除 {superset_count} 张Superset表")
            safe_print(f"     删除后表数将减少到: {total - superset_count} 张")
        
        if other_count > 0:
            safe_print(f"  2. 需要确认 {other_count} 张'其他表'的用途")
            safe_print(f"     如果不需要，可以删除")
        
        safe_print(f"\n  3. 项目必需表: {project_count + finance_count + views_count} 张")
        safe_print(f"     这些表应该保留")
        
        # 保存详细列表到文件
        output_file = Path(__file__).parent.parent / "temp" / "development" / "table_analysis_report.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Public Schema表分析报告\n")
            f.write(f"="*80 + "\n")
            f.write(f"总表数: {total}\n\n")
            
            for category, tables in categories.items():
                f.write(f"\n[{category.upper()}] {len(tables)} 张表:\n")
                for table in tables:
                    f.write(f"  - {table}\n")
        
        safe_print(f"\n详细报告已保存到: {output_file}")
        
    except Exception as e:
        safe_print(f"[ERROR] 分析过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    analyze_all_tables()

