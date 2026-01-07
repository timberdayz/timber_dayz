"""
v4.19.0: 添加通知优先级字段的数据库迁移脚本

直接执行SQL添加 notifications 表的 priority 字段
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.models.database import SessionLocal


def add_notification_priority_field():
    """添加通知优先级字段"""
    db = SessionLocal()
    
    try:
        # 检查字段是否已存在
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'notifications' AND column_name = 'priority'
        """))
        
        if result.fetchone():
            print("[INFO] priority field already exists in notifications table, skipping")
            return True
        
        # 添加 priority 字段
        print("[INFO] Adding priority field to notifications table...")
        db.execute(text("""
            ALTER TABLE notifications 
            ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'medium'
        """))
        print("[OK] priority field added successfully")
        
        # 添加索引
        print("[INFO] Creating index on priority field...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_notifications_priority 
            ON notifications(priority)
        """))
        print("[OK] Index created successfully")
        
        # 添加字段注释
        print("[INFO] Adding column comment...")
        db.execute(text("""
            COMMENT ON COLUMN notifications.priority IS 'Priority: high, medium, low'
        """))
        print("[OK] Column comment added successfully")
        
        # 提交事务
        db.commit()
        print("[OK] All changes committed successfully")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to add priority field: {e}")
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("v4.19.0: Add notification priority field")
    print("=" * 50)
    
    success = add_notification_priority_field()
    
    if success:
        print("\n[OK] Migration completed successfully")
    else:
        print("\n[FAIL] Migration failed")
        sys.exit(1)

