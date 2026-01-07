#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新price字段的同义词，添加"单价"相关词汇
"""

import sys
from pathlib import Path
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text

def main():
    print("=== Update price field synonyms ===\n")
    
    with engine.connect() as conn:
        # 获取当前price字段的synonyms
        result = conn.execute(text("""
            SELECT field_code, cn_name, synonyms
            FROM field_mapping_dictionary
            WHERE field_code = 'price'
        """))
        row = result.fetchone()
        
        if not row:
            print("[ERROR] price field not found in dictionary")
            return
        
        print(f"Current field: {row[0]} ({row[1]})")
        current_synonyms = row[2] if row[2] else []
        print(f"Current synonyms: {current_synonyms}")
        
        # 确保synonyms是list
        if isinstance(current_synonyms, str):
            current_synonyms = json.loads(current_synonyms)
        elif not isinstance(current_synonyms, list):
            current_synonyms = []
        
        # 添加新同义词
        new_synonyms_to_add = [
            "price", "Price", "unit_price", "unit Price",
            "dan_jia", "dan jia"
        ]
        
        for syn in new_synonyms_to_add:
            if syn not in current_synonyms:
                current_synonyms.append(syn)
        
        # 去重
        current_synonyms = list(set(current_synonyms))
        
        print(f"\nUpdated synonyms: {current_synonyms}")
        
        # 更新数据库
        synonyms_json = json.dumps(current_synonyms, ensure_ascii=False)
        # 使用字符串替换而不是参数绑定（避免::jsonb语法问题）
        sql = f"""
            UPDATE field_mapping_dictionary
            SET synonyms = '{synonyms_json}'::jsonb,
                updated_at = NOW()
            WHERE field_code = 'price'
        """
        conn.execute(text(sql))
        conn.commit()
        
        print("\n[OK] Price field synonyms updated successfully")
        
        # 验证
        result = conn.execute(text("""
            SELECT synonyms
            FROM field_mapping_dictionary
            WHERE field_code = 'price'
        """))
        row = result.fetchone()
        print(f"\nVerified synonyms: {row[0]}")

if __name__ == "__main__":
    main()

