#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接执行通知配置表迁移脚本
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
    """执行通知配置表迁移"""
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
            # 检查并创建 smtp_config 表
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'smtp_config'
                );
            """)
            result = conn.execute(check_table)
            table_exists = result.scalar()
            
            if not table_exists:
                print("[INFO] Creating smtp_config table...")
                conn.execute(text("""
                    CREATE TABLE smtp_config (
                        id SERIAL PRIMARY KEY,
                        smtp_server VARCHAR(256) NOT NULL,
                        smtp_port INTEGER NOT NULL,
                        use_tls BOOLEAN NOT NULL DEFAULT TRUE,
                        username VARCHAR(256) NOT NULL,
                        password_encrypted TEXT NOT NULL,
                        from_email VARCHAR(256) NOT NULL,
                        from_name VARCHAR(128),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_by INTEGER,
                        CONSTRAINT fk_smtp_config_updated_by FOREIGN KEY (updated_by) 
                            REFERENCES dim_users(user_id)
                    );
                """))
                conn.commit()
                print("[OK] smtp_config table created successfully")
            else:
                print("[INFO] smtp_config table already exists, skipping")
            
            # 检查并创建 notification_templates 表
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'notification_templates'
                );
            """)
            result = conn.execute(check_table)
            table_exists = result.scalar()
            
            if not table_exists:
                print("[INFO] Creating notification_templates table...")
                conn.execute(text("""
                    CREATE TABLE notification_templates (
                        id SERIAL PRIMARY KEY,
                        template_name VARCHAR(128) UNIQUE NOT NULL,
                        template_type VARCHAR(64) NOT NULL,
                        subject VARCHAR(256),
                        content TEXT NOT NULL,
                        variables JSONB,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        created_by INTEGER,
                        updated_by INTEGER,
                        CONSTRAINT fk_notification_templates_created_by FOREIGN KEY (created_by) 
                            REFERENCES dim_users(user_id),
                        CONSTRAINT fk_notification_templates_updated_by FOREIGN KEY (updated_by) 
                            REFERENCES dim_users(user_id)
                    );
                """))
                conn.execute(text("CREATE INDEX ix_notification_templates_template_name ON notification_templates(template_name);"))
                conn.execute(text("CREATE INDEX ix_notification_templates_template_type ON notification_templates(template_type);"))
                conn.commit()
                print("[OK] notification_templates table created successfully")
            else:
                print("[INFO] notification_templates table already exists, skipping")
            
            # 检查并创建 alert_rules 表
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alert_rules'
                );
            """)
            result = conn.execute(check_table)
            table_exists = result.scalar()
            
            if not table_exists:
                print("[INFO] Creating alert_rules table...")
                conn.execute(text("""
                    CREATE TABLE alert_rules (
                        id SERIAL PRIMARY KEY,
                        rule_name VARCHAR(128) UNIQUE NOT NULL,
                        rule_type VARCHAR(64) NOT NULL,
                        condition JSONB NOT NULL,
                        template_id INTEGER,
                        recipients JSONB,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        priority VARCHAR(16) NOT NULL DEFAULT 'medium',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        created_by INTEGER,
                        updated_by INTEGER,
                        CONSTRAINT fk_alert_rules_template_id FOREIGN KEY (template_id) 
                            REFERENCES notification_templates(id),
                        CONSTRAINT fk_alert_rules_created_by FOREIGN KEY (created_by) 
                            REFERENCES dim_users(user_id),
                        CONSTRAINT fk_alert_rules_updated_by FOREIGN KEY (updated_by) 
                            REFERENCES dim_users(user_id)
                    );
                """))
                conn.execute(text("CREATE INDEX ix_alert_rules_rule_name ON alert_rules(rule_name);"))
                conn.execute(text("CREATE INDEX ix_alert_rules_rule_type ON alert_rules(rule_type);"))
                conn.execute(text("CREATE INDEX ix_alert_rules_enabled ON alert_rules(enabled);"))
                conn.commit()
                print("[OK] alert_rules table created successfully")
            else:
                print("[INFO] alert_rules table already exists, skipping")
            
            return True
            
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
