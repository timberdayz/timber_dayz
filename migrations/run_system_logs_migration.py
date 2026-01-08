#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接执行系统日志表迁移脚本
避免alembic.ini编码问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
import os

def run_migration():
    """执行系统日志表迁移"""
    settings = get_settings()
    
    # 获取数据库URL
    database_url = settings.DATABASE_URL
    if not database_url:
        print("[ERROR] DATABASE_URL not found in environment")
        return False
    
    print(f"[INFO] Connecting to database...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # 检查表是否已存在
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'system_logs'
                );
            """)
            result = conn.execute(check_table)
            table_exists = result.scalar()
            
            if table_exists:
                print("[INFO] system_logs table already exists, skipping migration")
                return True
            
            print("[INFO] Creating system_logs table...")
            
            # 创建表
            create_table = text("""
                CREATE TABLE system_logs (
                    id SERIAL PRIMARY KEY,
                    level VARCHAR(10) NOT NULL,
                    module VARCHAR(64) NOT NULL,
                    message TEXT NOT NULL,
                    user_id INTEGER,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(512),
                    details JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_system_logs_user_id FOREIGN KEY (user_id) 
                        REFERENCES dim_users(user_id)
                );
            """)
            conn.execute(create_table)
            
            # 创建索引
            print("[INFO] Creating indexes...")
            conn.execute(text("CREATE INDEX ix_system_logs_level ON system_logs(level);"))
            conn.execute(text("CREATE INDEX ix_system_logs_module ON system_logs(module);"))
            conn.execute(text("CREATE INDEX ix_system_logs_created_at ON system_logs(created_at);"))
            
            conn.commit()
            print("[OK] system_logs table created successfully")
            return True
            
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
