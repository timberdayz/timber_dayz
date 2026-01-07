# -*- coding: utf-8 -*-
"""
查询inventory域物化视图当前字段，并根据is_mv_display配置更新视图
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def check_mv_fields():
    """检查物化视图当前字段"""
    safe_print("=" * 80)
    safe_print("检查库存物化视图字段")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 查询is_mv_display=true的inventory域字段
        safe_print("\n[1] 查询is_mv_display=true的inventory域字段...")
        mv_fields_sql = """
            SELECT field_code, cn_name, field_group, data_type
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
              AND is_mv_display = true
            ORDER BY field_group, field_code
        """
        mv_fields_result = db.execute(text(mv_fields_sql)).fetchall()
        
        mv_field_codes = [row[0] for row in mv_fields_result]
        safe_print(f"\n物化视图应包含的字段 ({len(mv_field_codes)}个):")
        for row in mv_fields_result:
            field_code, cn_name, field_group, data_type = row
            safe_print(f"  - {field_code} ({cn_name}) [{field_group}]")
        
        # 2. 检查fact_product_metrics表的实际字段
        safe_print("\n[2] 检查fact_product_metrics表的实际字段...")
        table_columns_sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_product_metrics'
              AND column_name IN :field_codes
            ORDER BY column_name
        """
        # 注意：PostgreSQL的IN子句需要特殊处理
        placeholders = ','.join([f"'{code}'" for code in mv_field_codes])
        table_columns_sql = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_product_metrics'
              AND column_name IN ({placeholders})
            ORDER BY column_name
        """
        table_columns_result = db.execute(text(table_columns_sql)).fetchall()
        
        existing_columns = {row[0]: row[1] for row in table_columns_result}
        safe_print(f"\nfact_product_metrics表中存在的字段 ({len(existing_columns)}个):")
        for col_name, col_type in existing_columns.items():
            safe_print(f"  - {col_name} ({col_type})")
        
        # 3. 检查缺失的字段
        missing_fields = set(mv_field_codes) - set(existing_columns.keys())
        if missing_fields:
            safe_print(f"\n[WARNING] 以下字段在辞典中标记为MV显示，但表中不存在:")
            for field in missing_fields:
                safe_print(f"  - {field}")
        else:
            safe_print("\n[OK] 所有标记为MV显示的字段都在表中存在")
        
        # 4. 检查当前物化视图的字段
        safe_print("\n[3] 检查当前物化视图的字段...")
        
        # 检查mv_inventory_by_sku
        try:
            mv_sku_columns_sql = """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'mv_inventory_by_sku'
                ORDER BY ordinal_position
            """
            mv_sku_result = db.execute(text(mv_sku_columns_sql)).fetchall()
            mv_sku_columns = [row[0] for row in mv_sku_result]
            safe_print(f"\nmv_inventory_by_sku当前字段 ({len(mv_sku_columns)}个):")
            for col in mv_sku_columns:
                safe_print(f"  - {col}")
        except Exception as e:
            safe_print(f"\n[WARNING] mv_inventory_by_sku视图不存在或查询失败: {e}")
            mv_sku_columns = []
        
        # 检查mv_inventory_summary
        try:
            mv_summary_columns_sql = """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'mv_inventory_summary'
                ORDER BY ordinal_position
            """
            mv_summary_result = db.execute(text(mv_summary_columns_sql)).fetchall()
            mv_summary_columns = [row[0] for row in mv_summary_result]
            safe_print(f"\nmv_inventory_summary当前字段 ({len(mv_summary_columns)}个):")
            for col in mv_summary_columns:
                safe_print(f"  - {col}")
        except Exception as e:
            safe_print(f"\n[WARNING] mv_inventory_summary视图不存在或查询失败: {e}")
            mv_summary_columns = []
        
        safe_print("\n" + "=" * 80)
        safe_print("检查完成！")
        safe_print("=" * 80)
        
        return {
            'mv_field_codes': mv_field_codes,
            'existing_columns': existing_columns,
            'missing_fields': missing_fields,
            'mv_sku_columns': mv_sku_columns,
            'mv_summary_columns': mv_summary_columns
        }
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    check_mv_fields()

