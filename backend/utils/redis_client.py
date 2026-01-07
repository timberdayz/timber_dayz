#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis缓存客户端（v4.6.3）

功能：
1. FastAPI缓存集成
2. 缓存策略管理
3. 智能降级（Redis不可用时自动禁用缓存）

使用方法：
    from backend.utils.redis_client import init_redis
    
    # 在main.py的lifespan中初始化
    await init_redis(app)
"""

import os
from typing import Optional
from redis import asyncio as aioredis
from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from modules.core.logger import get_logger

logger = get_logger(__name__)


async def init_redis(app: Optional[FastAPI] = None) -> Optional[aioredis.Redis]:
    """
    初始化Redis缓存
    
    参数:
        app: FastAPI应用实例（可选）
    
    返回:
        Redis客户端或None（如果Redis不可用）
    
    注意:
        如果Redis不可用，会自动降级，不影响系统运行
    """
    try:
        # 从环境变量读取Redis配置
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        # 连接Redis
        redis = await aioredis.from_url(
            redis_url,
            encoding="utf8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        
        # 测试连接
        await redis.ping()
        
        # 初始化FastAPI缓存
        FastAPICache.init(
            RedisBackend(redis),
            prefix="xihong-erp:"
        )
        
        logger.info(f"[OK] Redis缓存已启用: {redis_url}")
        
        # 如果提供了app，将redis实例保存到app.state
        if app:
            app.state.redis = redis
        
        return redis
    
    except Exception as e:
        logger.warning(f"[SKIP] Redis连接失败，缓存未启用: {e}")
        logger.warning("      系统将继续运行，但无缓存加速")
        logger.warning("      启动Redis: docker run -d -p 6379:6379 redis:alpine")
        return None


async def get_redis_client(app: FastAPI) -> Optional[aioredis.Redis]:
    """
    获取Redis客户端
    
    参数:
        app: FastAPI应用实例
    
    返回:
        Redis客户端或None
    """
    return getattr(app.state, 'redis', None)


async def clear_cache(pattern: str = "*", app: Optional[FastAPI] = None):
    """
    清除缓存
    
    参数:
        pattern: 缓存key模式（如 "xihong-erp:field-*"）
        app: FastAPI应用实例
    
    示例:
        # 清除所有字段辞典缓存
        await clear_cache("xihong-erp:field-*", app)
    """
    try:
        if app and hasattr(app.state, 'redis'):
            redis = app.state.redis
            # 查找匹配的keys
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
                logger.info(f"[Cache] 清除 {len(keys)} 个缓存: {pattern}")
        else:
            logger.debug("[Cache] Redis未启用，跳过清除缓存")
    
    except Exception as e:
        logger.error(f"[Cache] 清除缓存失败: {e}")
