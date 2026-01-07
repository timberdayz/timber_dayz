# -*- coding: utf-8 -*-
"""
验证物化视图字段（使用pg_attribute查询）
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

def verify_mv_columns():
    """验证物化视图字段"""
    safe_print("=" * 80)
    safe_print("验证物化视图字段")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 使用pg_attribute查询
        safe_print("\n[1] 查询mv_inventory_by_sku视图字段（使用pg_attribute）...")
        columns_sql = """
            SELECT a.attname, t.typname
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_type t ON a.atttypid = t.oid
            WHERE c.relname = 'mv_inventory_by_sku'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
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
    verify_mv_columns()

