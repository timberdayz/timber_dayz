# -*- coding: utf-8 -*-
"""
检查库存物化视图字段配置问题
1. 为什么有店铺ID和平台代码？
2. 为什么商品名称没有显示？
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

def check_inventory_mv_issues():
    """检查库存物化视图问题"""
    safe_print("=" * 80)
    safe_print("检查库存物化视图字段配置问题")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 检查字段映射中inventory域的所有字段及其is_mv_display状态
        safe_print("\n[1] 检查字段映射中inventory域的所有字段...")
        all_fields_sql = """
            SELECT field_code, cn_name, field_group, is_mv_display, is_required
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
            ORDER BY 
                CASE field_group
                    WHEN 'dimension' THEN 1
                    WHEN 'datetime' THEN 2
                    WHEN 'metric' THEN 3
                    ELSE 4
                END,
                field_code
        """
        all_fields_result = db.execute(text(all_fields_sql)).fetchall()
        
        safe_print(f"\ninventory域所有字段 ({len(all_fields_result)}个):")
        safe_print("-" * 80)
        for row in all_fields_result:
            field_code, cn_name, field_group, is_mv_display, is_required = row
            mv_mark = "[MV显示]" if is_mv_display else "[不显示]"
            required_mark = "[必填]" if is_required else ""
            safe_print(f"  {mv_mark} {field_code:30} ({cn_name:20}) [{field_group:10}] {required_mark}")
        
        # 2. 检查fact_product_metrics表中实际存在的字段
        safe_print("\n[2] 检查fact_product_metrics表中实际存在的字段...")
        table_columns_sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_product_metrics'
              AND table_schema = 'public'
            ORDER BY ordinal_position
        """
        table_columns_result = db.execute(text(table_columns_sql)).fetchall()
        
        safe_print(f"\nfact_product_metrics表字段 ({len(table_columns_result)}个):")
        safe_print("-" * 80)
        for col_name, col_type in table_columns_result:
            safe_print(f"  - {col_name:30} ({col_type})")
        
        # 3. 检查商品名称相关字段
        safe_print("\n[3] 检查商品名称相关字段...")
        product_name_fields = [row for row in all_fields_result if 'name' in row[0].lower() or '名称' in row[1]]
        
        if product_name_fields:
            safe_print("\n商品名称相关字段:")
            for row in product_name_fields:
                field_code, cn_name, field_group, is_mv_display, is_required = row
                exists_in_table = any(col[0] == field_code for col in table_columns_result)
                mv_mark = "[MV显示]" if is_mv_display else "[不显示]"
                exists_mark = "[表中存在]" if exists_in_table else "[表中不存在]"
                safe_print(f"  {mv_mark} {exists_mark} {field_code:30} ({cn_name:20})")
        else:
            safe_print("\n[WARNING] 未找到商品名称相关字段！")
        
        # 4. 检查当前物化视图的字段
        safe_print("\n[4] 检查当前物化视图的字段...")
        mv_columns_sql = """
            SELECT a.attname, t.typname
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_type t ON a.atttypid = t.oid
            WHERE c.relname = 'mv_inventory_by_sku'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
        """
        mv_columns_result = db.execute(text(mv_columns_sql)).fetchall()
        
        safe_print(f"\nmv_inventory_by_sku视图字段 ({len(mv_columns_result)}个):")
        safe_print("-" * 80)
        for col_name, col_type in mv_columns_result:
            safe_print(f"  - {col_name:30} ({col_type})")
        
        # 5. 分析问题
        safe_print("\n" + "=" * 80)
        safe_print("问题分析")
        safe_print("=" * 80)
        
        # 检查商品名称字段
        product_name_in_dict = [row for row in all_fields_result if row[0] == 'product_name']
        product_name_in_table = any(col[0] == 'product_name' for col in table_columns_result)
        product_name_in_mv = any(col[0] == 'product_name' for col in mv_columns_result)
        
        safe_print(f"""
问题1: 为什么有店铺ID和平台代码？
- 当前物化视图包含: platform_code, shop_id
- 这些是维度字段（dimension），用于数据分组和筛选
- 但您说得对，库存视图的核心应该是：SKU、商品名称、数量
- 建议：保留这些字段作为筛选维度，但确保核心字段（SKU、商品名称、数量）优先显示

问题2: 为什么商品名称没有显示？
- 字段映射中是否有product_name字段: {'是' if product_name_in_dict else '否'}
- fact_product_metrics表中是否有product_name字段: {'是' if product_name_in_table else '否'}
- mv_inventory_by_sku视图中是否有product_name字段: {'是' if product_name_in_mv else '否'}
        """)
        
        if product_name_in_dict:
            field_info = product_name_in_dict[0]
            safe_print(f"\n字段映射中的product_name信息:")
            safe_print(f"  - field_code: {field_info[0]}")
            safe_print(f"  - cn_name: {field_info[1]}")
            safe_print(f"  - field_group: {field_info[2]}")
            safe_print(f"  - is_mv_display: {field_info[3]}")
            safe_print(f"  - is_required: {field_info[4]}")
        
        if not product_name_in_table:
            safe_print("\n[原因] product_name字段在fact_product_metrics表中不存在！")
            safe_print("       可能的原因：")
            safe_print("       1. 数据入库时product_name被映射到了其他字段名")
            safe_print("       2. product_name存储在attributes JSONB列中")
            safe_print("       3. 需要检查字段映射配置，确认product_name对应的数据库列名")
        
        if product_name_in_dict and product_name_in_dict[0][3] and not product_name_in_mv:
            safe_print("\n[原因] product_name字段标记为MV显示，但物化视图中没有包含！")
            safe_print("       需要重新生成物化视图，包含product_name字段")
        
        safe_print("\n" + "=" * 80)
        safe_print("检查完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_inventory_mv_issues()

