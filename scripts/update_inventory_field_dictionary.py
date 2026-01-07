#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新字段映射辞典，将inventory域的platform_code和shop_id标记为可选
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def main():
    safe_print("\n" + "="*70)
    safe_print("更新字段映射辞典")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 更新inventory域的platform_code和shop_id为可选
        safe_print("\n[Step 1] 更新字段映射辞典...")
        update_query = text("""
            UPDATE field_mapping_dictionary 
            SET is_required = false,
                description = CASE 
                    WHEN field_code = 'platform_code' THEN '数据来源平台代码（inventory域允许为空，其他域必填）'
                    WHEN field_code = 'shop_id' THEN '店铺唯一标识符（inventory域允许为空，其他域必填）'
                    ELSE description
                END,
                updated_at = NOW()
            WHERE data_domain = 'inventory' 
              AND field_code IN ('platform_code', 'shop_id')
        """)
        result = db.execute(update_query)
        db.commit()
        updated_count = result.rowcount
        
        safe_print(f"  [OK] 更新了 {updated_count} 条记录")
        
        # 验证结果
        safe_print("\n[Step 2] 验证结果...")
        check_query = text("""
            SELECT field_code, cn_name, is_required, description
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory' 
              AND field_code IN ('platform_code', 'shop_id')
            ORDER BY field_code
        """)
        result = db.execute(check_query)
        rows = result.fetchall()
        
        safe_print("  字段状态:")
        for row in rows:
            required_status = "必填" if row[2] else "可选"
            safe_print(f"    - {row[1]} ({row[0]}): {required_status}")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] 字段映射辞典更新完成！")
        safe_print("="*70)
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

