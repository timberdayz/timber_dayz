#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证 notifications 表的 priority 字段是否存在
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.models.database import SessionLocal

def verify_priority_field():
    """验证 priority 字段是否存在"""
    db = SessionLocal()
    
    try:
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'notifications' AND column_name = 'priority'
        """))
        
        if result.fetchone():
            print("[OK] priority field exists in notifications table")
            return True
        else:
            print("[FAIL] priority field not found in notifications table")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to verify: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = verify_priority_field()
    sys.exit(0 if success else 1)

