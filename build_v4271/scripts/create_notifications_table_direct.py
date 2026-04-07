#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.19.0: 创建系统通知表（直接SQL执行）

功能：
1. 创建 notifications 表
2. 创建必要的索引
3. 添加字段注释

运行方式：
    python scripts/create_notifications_table_direct.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.models.database import SessionLocal


def create_notifications_table():
    """创建系统通知表"""
    db = SessionLocal()
    
    try:
        # 检查表是否已存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'notifications'
            )
        """))
        exists = result.scalar()
        
        if exists:
            print("[INFO] notifications table already exists, skipping creation")
            return True
        
        # 创建 notifications 表
        print("[INFO] Creating notifications table...")
        db.execute(text("""
            CREATE TABLE notifications (
                notification_id BIGSERIAL PRIMARY KEY,
                recipient_id BIGINT NOT NULL REFERENCES dim_users(user_id) ON DELETE CASCADE,
                notification_type VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                extra_data JSON,
                related_user_id BIGINT REFERENCES dim_users(user_id) ON DELETE SET NULL,
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                read_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        print("[OK] Table created successfully")
        
        # 创建索引
        print("[INFO] Creating indexes...")
        
        db.execute(text("""
            CREATE INDEX idx_notification_recipient 
            ON notifications(recipient_id)
        """))
        
        db.execute(text("""
            CREATE INDEX idx_notification_type 
            ON notifications(notification_type)
        """))
        
        db.execute(text("""
            CREATE INDEX idx_notification_is_read 
            ON notifications(is_read)
        """))
        
        db.execute(text("""
            CREATE INDEX idx_notification_created_at 
            ON notifications(created_at)
        """))
        
        db.execute(text("""
            CREATE INDEX idx_notification_user_unread 
            ON notifications(recipient_id, is_read)
        """))
        
        db.execute(text("""
            CREATE INDEX idx_notification_type_created 
            ON notifications(notification_type, created_at)
        """))
        
        print("[OK] Indexes created successfully")
        
        # 添加字段注释
        print("[INFO] Adding column comments...")
        
        db.execute(text("""
            COMMENT ON TABLE notifications IS 'v4.19.0: System notifications table'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.notification_id IS 'Notification primary key'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.recipient_id IS 'Recipient user ID'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.notification_type IS 'Type: user_registered, user_approved, user_rejected, system_alert'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.title IS 'Notification title'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.content IS 'Notification content'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.extra_data IS 'Extended data in JSON format'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.related_user_id IS 'Related user ID (e.g., the approved user)'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.is_read IS 'Whether the notification has been read'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.read_at IS 'Time when the notification was read'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN notifications.created_at IS 'Notification creation time'
        """))
        
        print("[OK] Column comments added successfully")
        
        # 提交事务
        db.commit()
        print("[OK] All changes committed successfully")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to create notifications table: {e}")
        return False
        
    finally:
        db.close()


def verify_table():
    """验证表结构"""
    db = SessionLocal()
    
    try:
        print("\n[INFO] Verifying table structure...")
        
        # 查询表结构
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'notifications'
            ORDER BY ordinal_position
        """))
        
        columns = result.fetchall()
        
        print("\n[INFO] Table columns:")
        print("-" * 70)
        for col in columns:
            print(f"  {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")
        print("-" * 70)
        
        # 查询索引
        result = db.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'notifications'
        """))
        
        indexes = result.fetchall()
        
        print("\n[INFO] Table indexes:")
        print("-" * 70)
        for idx in indexes:
            print(f"  {idx[0]}")
        print("-" * 70)
        
        print("\n[OK] Table verification completed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Verification failed: {e}")
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("v4.19.0: Create Notifications Table")
    print("=" * 70)
    
    if create_notifications_table():
        verify_table()
        print("\n[OK] Migration completed successfully!")
    else:
        print("\n[FAIL] Migration failed!")
        sys.exit(1)

