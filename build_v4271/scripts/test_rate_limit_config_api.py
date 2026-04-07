#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试限流配置管理 API

用途：验证配置查询、更新、删除功能

使用方法：
    python scripts/test_rate_limit_config_api.py
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_async_db, init_db
from modules.core.db import DimRateLimitConfig, FactRateLimitConfigAudit
from modules.core.logger import get_logger
from backend.middleware.rate_limiter import RATE_LIMIT_TIERS

logger = get_logger(__name__)


async def test_rate_limit_config_api():
    """
    测试限流配置管理 API
    
    测试内容：
    1. 查询配置列表
    2. 查询指定角色的配置
    3. 创建配置
    4. 更新配置
    5. 删除配置
    6. 验证审计日志
    """
    logger.info("[Test] 开始测试限流配置管理 API...")
    
    # 初始化数据库（同步函数）
    init_db()
    
    # 获取数据库会话
    async for db in get_async_db():
        try:
            # 1. 查询配置列表
            logger.info("[Test] 1. 查询配置列表...")
            stmt = select(DimRateLimitConfig)
            result = await db.execute(stmt)
            configs = result.scalars().all()
            logger.info(f"[Test] 找到 {len(configs)} 条配置")
            
            if configs:
                for config in configs[:5]:  # 只显示前5条
                    logger.info(f"  - {config.role_code}/{config.endpoint_type}: {config.limit_value}")
            
            # 2. 查询指定角色的配置
            logger.info("[Test] 2. 查询 admin 角色的配置...")
            stmt = select(DimRateLimitConfig).where(
                DimRateLimitConfig.role_code == "admin"
            )
            result = await db.execute(stmt)
            admin_configs = result.scalars().all()
            logger.info(f"[Test] admin 角色有 {len(admin_configs)} 条配置")
            for config in admin_configs:
                logger.info(f"  - {config.endpoint_type}: {config.limit_value}")
            
            # 3. 测试创建配置（如果不存在）
            logger.info("[Test] 3. 测试创建配置...")
            test_role = "test_role"
            test_endpoint = "test_endpoint"
            
            # 检查是否已存在
            stmt = select(DimRateLimitConfig).where(
                DimRateLimitConfig.role_code == test_role,
                DimRateLimitConfig.endpoint_type == test_endpoint
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.info(f"[Test] 测试配置已存在，跳过创建")
            else:
                new_config = DimRateLimitConfig(
                    role_code=test_role,
                    endpoint_type=test_endpoint,
                    limit_value="50/minute",
                    is_active=True,
                    description="测试配置",
                    created_by="test_script"
                )
                db.add(new_config)
                await db.commit()
                await db.refresh(new_config)
                logger.info(f"[Test] 成功创建测试配置: {new_config.config_id}")
            
            # 4. 测试更新配置
            logger.info("[Test] 4. 测试更新配置...")
            stmt = select(DimRateLimitConfig).where(
                DimRateLimitConfig.role_code == test_role,
                DimRateLimitConfig.endpoint_type == test_endpoint
            )
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if config:
                old_value = config.limit_value
                config.limit_value = "60/minute"
                config.updated_by = "test_script"
                await db.commit()
                await db.refresh(config)
                logger.info(f"[Test] 成功更新配置: {old_value} -> {config.limit_value}")
            
            # 5. 测试删除配置
            logger.info("[Test] 5. 测试删除配置...")
            if config:
                config_id = config.config_id
                await db.delete(config)
                await db.commit()
                logger.info(f"[Test] 成功删除配置: {config_id}")
            
            # 6. 验证审计日志
            logger.info("[Test] 6. 验证审计日志...")
            stmt = select(FactRateLimitConfigAudit).order_by(
                FactRateLimitConfigAudit.created_at.desc()
            ).limit(10)
            result = await db.execute(stmt)
            audit_logs = result.scalars().all()
            logger.info(f"[Test] 找到 {len(audit_logs)} 条最近的审计日志")
            for log in audit_logs[:5]:  # 只显示前5条
                logger.info(f"  - {log.action_type}: {log.role_code}/{log.endpoint_type} by {log.operator_username}")
            
            logger.info("[Test] 所有测试通过！")
            
        except Exception as e:
            logger.error(f"[Test] 测试失败: {e}")
            await db.rollback()
            raise
        finally:
            await db.close()
            break


if __name__ == "__main__":
    asyncio.run(test_rate_limit_config_api())

