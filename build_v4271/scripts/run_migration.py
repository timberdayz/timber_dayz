#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
运行数据库迁移脚本

用途：直接使用 Python 运行迁移，避免编码问题
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import get_async_db, init_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def run_migration():
    """运行迁移：创建限流配置表"""
    logger.info("[Migration] 开始运行数据库迁移...")
    
    # 初始化数据库（同步函数）
    init_db()
    
    # 获取数据库会话
    async for db in get_async_db():
        try:
            # 检查表是否已存在
            check_table_sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'dim_rate_limit_config'
            );
            """
            result = await db.execute(text(check_table_sql))
            table_exists = result.scalar()
            
            if table_exists:
                logger.info("[Migration] 限流配置表已存在，跳过迁移")
                return
            
            logger.info("[Migration] 创建限流配置表...")
            
            # 创建 dim_rate_limit_config 表
            create_config_table_sql = """
            CREATE TABLE dim_rate_limit_config (
                config_id SERIAL PRIMARY KEY,
                role_code VARCHAR(50) NOT NULL,
                endpoint_type VARCHAR(50) NOT NULL,
                limit_value VARCHAR(50) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                description TEXT,
                created_by VARCHAR(100),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_by VARCHAR(100),
                CONSTRAINT uq_rate_limit_config_role_endpoint UNIQUE (role_code, endpoint_type)
            );
            """
            await db.execute(text(create_config_table_sql))
            
            # 创建索引
            create_indexes_sql = [
                "CREATE INDEX ix_rate_limit_config_active ON dim_rate_limit_config (is_active, role_code);",
                "CREATE INDEX ix_rate_limit_config_role ON dim_rate_limit_config (role_code, endpoint_type);",
                "CREATE INDEX ix_dim_rate_limit_config_role_code ON dim_rate_limit_config (role_code);",
                "CREATE INDEX ix_dim_rate_limit_config_endpoint_type ON dim_rate_limit_config (endpoint_type);"
            ]
            for sql in create_indexes_sql:
                await db.execute(text(sql))
            
            # 创建 fact_rate_limit_config_audit 表
            create_audit_table_sql = """
            CREATE TABLE fact_rate_limit_config_audit (
                audit_id BIGSERIAL PRIMARY KEY,
                config_id INTEGER,
                role_code VARCHAR(50) NOT NULL,
                endpoint_type VARCHAR(50) NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                old_limit_value VARCHAR(50),
                new_limit_value VARCHAR(50),
                old_is_active BOOLEAN,
                new_is_active BOOLEAN,
                operator_id BIGINT,
                operator_username VARCHAR(100) NOT NULL,
                ip_address VARCHAR(50),
                user_agent VARCHAR(500),
                is_success BOOLEAN NOT NULL DEFAULT TRUE,
                error_message TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT fk_rate_limit_audit_config FOREIGN KEY (config_id) REFERENCES dim_rate_limit_config(config_id),
                CONSTRAINT fk_rate_limit_audit_operator FOREIGN KEY (operator_id) REFERENCES dim_users(user_id)
            );
            """
            await db.execute(text(create_audit_table_sql))
            
            # 创建审计表索引
            create_audit_indexes_sql = [
                "CREATE INDEX idx_rate_limit_audit_config ON fact_rate_limit_config_audit (config_id, created_at);",
                "CREATE INDEX idx_rate_limit_audit_role ON fact_rate_limit_config_audit (role_code, endpoint_type, created_at);",
                "CREATE INDEX idx_rate_limit_audit_operator ON fact_rate_limit_config_audit (operator_id, created_at);",
                "CREATE INDEX idx_rate_limit_audit_action ON fact_rate_limit_config_audit (action_type, created_at);",
                "CREATE INDEX ix_fact_rate_limit_config_audit_audit_id ON fact_rate_limit_config_audit (audit_id);",
                "CREATE INDEX ix_fact_rate_limit_config_audit_role_code ON fact_rate_limit_config_audit (role_code);",
                "CREATE INDEX ix_fact_rate_limit_config_audit_endpoint_type ON fact_rate_limit_config_audit (endpoint_type);",
                "CREATE INDEX ix_fact_rate_limit_config_audit_created_at ON fact_rate_limit_config_audit (created_at);"
            ]
            for sql in create_audit_indexes_sql:
                await db.execute(text(sql))
            
            await db.commit()
            logger.info("[Migration] 数据库迁移成功完成！")
            
        except Exception as e:
            logger.error(f"[Migration] 迁移失败: {e}")
            await db.rollback()
            raise
        finally:
            await db.close()
            break


if __name__ == "__main__":
    asyncio.run(run_migration())

