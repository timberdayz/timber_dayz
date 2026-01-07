# -*- coding: utf-8 -*-
"""
检查TikTok订单attributes中的实际字段名
"""

import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_attributes_fields():
    """检查attributes中的字段"""
    db = next(get_db())
    try:
        # 获取一个示例订单的attributes
        sample = db.execute(text("""
            SELECT order_id, attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            LIMIT 1
        """)).fetchone()
        
        if sample:
            order_id, attrs = sample
            safe_print(f"订单 {order_id} 的attributes字段:")
            safe_print(json.dumps(attrs, indent=2, ensure_ascii=False))
            
            # 检查shop_id和currency相关的字段
            safe_print("\n查找shop_id相关字段:")
            for key in attrs.keys():
                if 'shop' in key.lower() or '店铺' in key or 'store' in key.lower():
                    safe_print(f"  {key}: {attrs[key]}")
            
            safe_print("\n查找currency相关字段:")
            for key in attrs.keys():
                if 'currency' in key.lower() or '币种' in key or '货币' in key:
                    safe_print(f"  {key}: {attrs[key]}")
    finally:
        db.close()

if __name__ == "__main__":
    check_attributes_fields()

