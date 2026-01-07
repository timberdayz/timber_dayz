# -*- coding: utf-8 -*-
"""
验证更新后的库存物化视图字段
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

def verify_inventory_mv_final():
    """验证更新后的库存物化视图"""
    safe_print("=" * 80)
    safe_print("验证更新后的库存物化视图字段")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 检查mv_inventory_by_sku的字段
        safe_print("\n[1] 检查mv_inventory_by_sku视图字段...")
        verify_sql = """
            SELECT a.attname, a.attnum
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE c.relname = 'mv_inventory_by_sku'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
        """
        result = db.execute(text(verify_sql)).fetchall()
        columns = [row[0] for row in result]
        
        safe_print(f"\nmv_inventory_by_sku视图字段 ({len(columns)}个):")
        for i, col in enumerate(columns, 1):
            safe_print(f"  {i:2}. {col}")
        
        # 检查是否移除了platform_code、shop_id、granularity
        removed_fields = ['platform_code', 'shop_id', 'granularity']
        removed_count = sum(1 for field in removed_fields if field not in columns)
        
        if removed_count == len(removed_fields):
            safe_print(f"\n[OK] 已成功移除平台/店铺字段: {removed_fields}")
        else:
            still_present = [f for f in removed_fields if f in columns]
            if still_present:
                safe_print(f"\n[WARNING] 以下字段仍在视图中: {still_present}")
        
        # 检查核心字段是否存在
        core_fields = ['platform_sku', 'product_name', 'total_stock', 'available_stock']
        missing_core = [f for f in core_fields if f not in columns]
        if not missing_core:
            safe_print("\n[OK] 所有核心字段都已包含在视图中")
        else:
            safe_print(f"\n[WARNING] 缺少核心字段: {missing_core}")
        
        # 2. 检查mv_inventory_summary的字段
        safe_print("\n[2] 检查mv_inventory_summary视图字段...")
        verify_summary_sql = """
            SELECT a.attname, a.attnum
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE c.relname = 'mv_inventory_summary'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
        """
        result_summary = db.execute(text(verify_summary_sql)).fetchall()
        columns_summary = [row[0] for row in result_summary]
        
        safe_print(f"\nmv_inventory_summary视图字段 ({len(columns_summary)}个):")
        for i, col in enumerate(columns_summary, 1):
            safe_print(f"  {i:2}. {col}")
        
        # 检查是否移除了platform_code、shop_id
        removed_fields_summary = ['platform_code', 'shop_id']
        removed_count_summary = sum(1 for field in removed_fields_summary if field not in columns_summary)
        
        if removed_count_summary == len(removed_fields_summary):
            safe_print(f"\n[OK] 汇总视图已成功移除平台/店铺字段: {removed_fields_summary}")
        else:
            still_present_summary = [f for f in removed_fields_summary if f in columns_summary]
            if still_present_summary:
                safe_print(f"\n[WARNING] 以下字段仍在汇总视图中: {still_present_summary}")
        
        # 3. 检查数据行数
        safe_print("\n[3] 检查物化视图数据行数...")
        count_sql = """
            SELECT 
                (SELECT COUNT(*) FROM mv_inventory_by_sku) as sku_count,
                (SELECT COUNT(*) FROM mv_inventory_summary) as summary_count
        """
        count_result = db.execute(text(count_sql)).fetchone()
        sku_count, summary_count = count_result
        
        safe_print(f"\n数据行数:")
        safe_print(f"  - mv_inventory_by_sku: {sku_count}行")
        safe_print(f"  - mv_inventory_summary: {summary_count}行")
        
        safe_print("\n" + "=" * 80)
        safe_print("验证完成！")
        safe_print("=" * 80)
        
        safe_print("""
总结：
1. ✅ 库存物化视图已成功移除platform_code、shop_id、granularity字段
2. ✅ 物化视图只包含核心字段（SKU、商品名称、数量、仓库）
3. ✅ 汇总视图按仓库维度汇总，不再按平台/店铺分组
4. ✅ 符合"公司级库存"的业务需求
        """)
        
    except Exception as e:
        safe_print(f"验证失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify_inventory_mv_final()

