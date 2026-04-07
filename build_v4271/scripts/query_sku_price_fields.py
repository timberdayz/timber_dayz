#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询和修复SKU字段定义和价格字段映射问题
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def main():
    safe_print("\n" + "="*70)
    safe_print("查询SKU和价格字段定义")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 查询SKU相关字段
        safe_print("\n[1] SKU相关字段:")
        sku_query = text("""
            SELECT field_code, cn_name, en_name, data_domain, is_required, synonyms
            FROM field_mapping_dictionary
            WHERE field_code LIKE '%sku%' 
               OR cn_name LIKE '%SKU%' 
               OR cn_name LIKE '%规格%'
            ORDER BY data_domain, field_code
        """)
        result = db.execute(sku_query)
        sku_rows = result.fetchall()
        
        for row in sku_rows:
            safe_print(f"  - {row[1]} ({row[0]}) - {row[3]} - 必填:{row[4]}")
            if row[5]:
                safe_print(f"    同义词: {row[5]}")
        
        # 查询价格相关字段
        safe_print("\n[2] 价格相关字段:")
        price_query = text("""
            SELECT field_code, cn_name, en_name, data_domain, is_required
            FROM field_mapping_dictionary
            WHERE cn_name LIKE '%总价%' 
               OR cn_name LIKE '%单价%' 
               OR cn_name LIKE '%价格%'
            ORDER BY data_domain, field_code
        """)
        result = db.execute(price_query)
        price_rows = result.fetchall()
        
        for row in price_rows:
            safe_print(f"  - {row[1]} ({row[0]}) - {row[3]} - 必填:{row[4]}")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("查询完成")
        safe_print("="*70)
        
    except Exception as e:
        safe_print(f"\n[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

