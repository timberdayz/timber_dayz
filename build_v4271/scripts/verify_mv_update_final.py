# -*- coding: utf-8 -*-
"""
验证物化视图更新结果
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

def verify_mv_update():
    """验证物化视图更新结果"""
    safe_print("=" * 80)
    safe_print("验证物化视图更新结果")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 查询mv_inventory_by_sku的字段
        safe_print("\n[1] 查询mv_inventory_by_sku视图字段...")
        columns_sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'mv_inventory_by_sku'
            ORDER BY ordinal_position
        """
        columns_result = db.execute(text(columns_sql)).fetchall()
        
        safe_print(f"字段数: {len(columns_result)}个")
        safe_print("字段列表:")
        for col_name, col_type in columns_result:
            safe_print(f"  - {col_name} ({col_type})")
        
        # 查询数据行数
        count_sql = "SELECT COUNT(*) FROM mv_inventory_by_sku"
        row_count = db.execute(text(count_sql)).scalar()
        safe_print(f"\n数据行数: {row_count}")
        
        # 查询mv_inventory_summary的字段
        safe_print("\n[2] 查询mv_inventory_summary视图字段...")
        summary_columns_sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'mv_inventory_summary'
            ORDER BY ordinal_position
        """
        summary_columns_result = db.execute(text(summary_columns_sql)).fetchall()
        
        safe_print(f"字段数: {len(summary_columns_result)}个")
        safe_print("字段列表:")
        for col_name, col_type in summary_columns_result:
            safe_print(f"  - {col_name} ({col_type})")
        
        # 查询数据行数
        summary_count_sql = "SELECT COUNT(*) FROM mv_inventory_summary"
        summary_row_count = db.execute(text(summary_count_sql)).scalar()
        safe_print(f"\n数据行数: {summary_row_count}")
        
        safe_print("\n" + "=" * 80)
        safe_print("验证完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        safe_print(f"验证失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify_mv_update()

