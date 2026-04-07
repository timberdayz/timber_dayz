#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
初始化限流配置数据

用途：将默认限流配置写入数据库

使用方法：
    python scripts/init_rate_limit_config.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_async_db, init_db
from modules.core.db import DimRateLimitConfig
from modules.core.logger import get_logger
from backend.middleware.rate_limiter import RATE_LIMIT_TIERS
import asyncio

logger = get_logger(__name__)


async def init_rate_limit_config():
    """
    初始化限流配置数据
    
    将 RATE_LIMIT_TIERS 中的默认配置写入数据库
    """
    logger.info("[RateLimitConfig] 开始初始化限流配置数据...")
    
    # 初始化数据库（同步函数）
    init_db()
    
    # 获取数据库会话
    async for db in get_async_db():
        try:
            # 检查是否已有配置
            stmt = select(DimRateLimitConfig)
            result = await db.execute(stmt)
            existing_configs = result.scalars().all()
            
            if existing_configs:
                logger.warning(f"[RateLimitConfig] 数据库中已存在 {len(existing_configs)} 条配置，跳过初始化")
                return
            
            # 插入默认配置
            configs_to_insert = []
            for role_code, endpoint_configs in RATE_LIMIT_TIERS.items():
                for endpoint_type, limit_value in endpoint_configs.items():
                    config = DimRateLimitConfig(
                        role_code=role_code,
                        endpoint_type=endpoint_type,
                        limit_value=limit_value,
                        is_active=True,
                        description=f"{role_code} 角色的 {endpoint_type} 端点默认限流配置",
                        created_by="system"
                    )
                    configs_to_insert.append(config)
            
            # 批量插入
            db.add_all(configs_to_insert)
            await db.commit()
            
            logger.info(f"[RateLimitConfig] 成功初始化 {len(configs_to_insert)} 条限流配置")
            
            # 打印配置摘要
            logger.info("[RateLimitConfig] 配置摘要:")
            for role_code, endpoint_configs in RATE_LIMIT_TIERS.items():
                logger.info(f"  {role_code}:")
                for endpoint_type, limit_value in endpoint_configs.items():
                    logger.info(f"    {endpoint_type}: {limit_value}")
            
        except Exception as e:
            logger.error(f"[RateLimitConfig] 初始化失败: {e}")
            await db.rollback()
            raise
        finally:
            await db.close()
            break


if __name__ == "__main__":
    asyncio.run(init_rate_limit_config())

