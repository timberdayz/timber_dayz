#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接创建 user_sessions 表

用于会话管理功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy import create_engine, text, inspect
from backend.utils.config import get_settings

def safe_print(msg):
    """安全打印（避免Windows编码错误）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))

def create_user_sessions_table():
    """创建 user_sessions 表"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        trans = conn.begin()
        
        try:
            safe_print("[*] 检查 user_sessions 表...")
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if 'user_sessions' in tables:
                safe_print("[OK] user_sessions 表已存在，跳过创建")
                trans.rollback()
                return True
            
            safe_print("[*] 创建 user_sessions 表...")
            conn.execute(text("""
                CREATE TABLE user_sessions (
                    session_id VARCHAR(64) PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES dim_users(user_id),
                    device_info VARCHAR(255),
                    ip_address VARCHAR(45),
                    location VARCHAR(100),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    last_active_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    revoked_at TIMESTAMP,
                    revoked_reason VARCHAR(100)
                )
            """))
            
            safe_print("[*] 添加表注释...")
            conn.execute(text("COMMENT ON TABLE user_sessions IS '用户会话表（用于会话管理）'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.session_id IS '会话ID（Token的哈希值）'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.device_info IS '设备信息（User-Agent）'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.ip_address IS 'IP地址'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.location IS '登录位置（可选）'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.created_at IS '创建时间（登录时间）'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.expires_at IS '过期时间'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.last_active_at IS '最后活跃时间'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.is_active IS '是否有效'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.revoked_at IS '撤销时间'"))
            conn.execute(text("COMMENT ON COLUMN user_sessions.revoked_reason IS '撤销原因'"))
            
            safe_print("[*] 创建索引...")
            conn.execute(text("CREATE INDEX idx_session_user_active ON user_sessions(user_id, is_active)"))
            conn.execute(text("CREATE INDEX idx_session_expires ON user_sessions(expires_at)"))
            conn.execute(text("CREATE INDEX idx_sessions_user_id ON user_sessions(user_id)"))
            
            trans.commit()
            safe_print("[OK] user_sessions 表创建成功")
            return True
            
        except Exception as e:
            trans.rollback()
            safe_print(f"[ERROR] 创建表失败: {e}")
            return False
        finally:
            conn.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 数据库连接失败: {e}")
        return False

def verify():
    """验证迁移结果"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        safe_print("=" * 60)
        safe_print("验证迁移结果")
        safe_print("=" * 60)
        safe_print(f"  [OK] user_sessions表存在: {'user_sessions' in tables}")
        
        if 'user_sessions' in tables:
            columns = [col['name'] for col in inspector.get_columns('user_sessions')]
            safe_print(f"  [OK] 字段数量: {len(columns)}")
            safe_print(f"  [OK] 字段列表: {', '.join(columns)}")
        
        safe_print("=" * 60)
        
        if 'user_sessions' in tables:
            safe_print("[OK] 迁移验证通过")
            return True
        else:
            safe_print("[ERROR] 迁移验证失败")
            return False
            
    except Exception as e:
        safe_print(f"[ERROR] 验证失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("用户会话表 - 数据库迁移（直接SQL方式）")
    print("=" * 60)
    
    if create_user_sessions_table():
        if verify():
            print("\n[SUCCESS] 迁移完成")
            sys.exit(0)
        else:
            print("\n[ERROR] 验证失败")
            sys.exit(1)
    else:
        print("\n[ERROR] 迁移失败")
        sys.exit(1)

