#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.19.0: 创建用户通知偏好表（直接SQL执行）

功能：
1. 创建 user_notification_preferences 表
2. 创建必要的索引和唯一约束
3. 添加字段注释

运行方式：
    python scripts/create_user_notification_preferences_table_direct.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.models.database import SessionLocal


def create_user_notification_preferences_table():
    """创建用户通知偏好表"""
    db = SessionLocal()
    
    try:
        # 检查表是否已存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_notification_preferences'
            )
        """))
        exists = result.scalar()
        
        if exists:
            print("[INFO] user_notification_preferences table already exists, skipping creation")
            return True
        
        # 创建 user_notification_preferences 表
        print("[INFO] Creating user_notification_preferences table...")
        db.execute(text("""
            CREATE TABLE user_notification_preferences (
                preference_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES dim_users(user_id) ON DELETE CASCADE,
                notification_type VARCHAR(50) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                desktop_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_user_notification_preference UNIQUE (user_id, notification_type)
            )
        """))
        print("[OK] Table created successfully")
        
        # 创建索引
        print("[INFO] Creating indexes...")
        
        db.execute(text("""
            CREATE INDEX idx_user_notification_user 
            ON user_notification_preferences(user_id)
        """))
        
        print("[OK] Indexes created successfully")
        
        # 添加字段注释
        print("[INFO] Adding column comments...")
        
        db.execute(text("""
            COMMENT ON TABLE user_notification_preferences IS 'v4.19.0: User notification preferences table'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.preference_id IS 'Preference primary key'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.user_id IS 'User ID'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.notification_type IS 'Notification type: user_registered, user_approved, user_rejected, system_alert, etc.'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.enabled IS 'Whether to enable in-app notifications'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.desktop_enabled IS 'Whether to enable desktop notifications (browser native notifications)'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.created_at IS 'Creation time'
        """))
        
        db.execute(text("""
            COMMENT ON COLUMN user_notification_preferences.updated_at IS 'Last update time'
        """))
        
        print("[OK] Column comments added successfully")
        
        # 创建 updated_at 触发器（自动更新）
        print("[INFO] Creating updated_at trigger...")
        db.execute(text("""
            CREATE OR REPLACE FUNCTION update_user_notification_preferences_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        db.execute(text("""
            CREATE TRIGGER trigger_update_user_notification_preferences_updated_at
            BEFORE UPDATE ON user_notification_preferences
            FOR EACH ROW
            EXECUTE FUNCTION update_user_notification_preferences_updated_at();
        """))
        
        print("[OK] Trigger created successfully")
        
        # 提交事务
        db.commit()
        print("[OK] All changes committed successfully")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to create user_notification_preferences table: {e}")
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
            WHERE table_name = 'user_notification_preferences'
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
            WHERE tablename = 'user_notification_preferences'
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
    print("v4.19.0: Create User Notification Preferences Table")
    print("=" * 70)
    
    if create_user_notification_preferences_table():
        verify_table()
        print("\n[OK] Migration completed successfully!")
    else:
        print("\n[FAIL] Migration failed!")
        sys.exit(1)

