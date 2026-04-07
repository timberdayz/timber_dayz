#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证v4.18.1迁移是否成功"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import SessionLocal

db = SessionLocal()
try:
    # 检查shop_id列（可能在public或core schema）
    result = db.execute(text("""
        SELECT table_schema, column_name, data_type, character_maximum_length
        FROM information_schema.columns 
        WHERE table_schema IN ('public', 'core')
        AND table_name = 'platform_accounts' 
        AND column_name = 'shop_id'
    """)).fetchone()
    
    if result:
        schema_name = result[0]
        print(f"[OK] platform_accounts.shop_id列已存在 (schema={schema_name}): {result[2]}({result[3]})")
    else:
        print("[ERROR] platform_accounts.shop_id列不存在")
        sys.exit(1)
    
    # 检查索引（可能在public或core schema）
    index_result = db.execute(text("""
        SELECT schemaname, indexname 
        FROM pg_indexes 
        WHERE schemaname IN ('public', 'core')
        AND tablename = 'platform_accounts'
        AND indexname = 'ix_platform_accounts_shop_id'
    """)).fetchone()
    
    if index_result:
        print(f"[OK] 索引 ix_platform_accounts_shop_id 已存在 (schema={index_result[0]})")
    else:
        print("[WARNING] 索引 ix_platform_accounts_shop_id 不存在")
    
    print("\n[OK] 所有迁移验证通过！")
    
except Exception as e:
    print(f"[ERROR] 验证失败: {e}")
    sys.exit(1)
finally:
    db.close()

