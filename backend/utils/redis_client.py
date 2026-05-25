#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 缓存客户端。

职责：
1. 初始化 Redis 连接
2. 可选接入 FastAPI Cache
3. Redis 不可用时优雅降级
"""

import os
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from redis import asyncio as aioredis

from modules.core.logger import get_logger

logger = get_logger(__name__)

try:
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.redis import RedisBackend

    FASTAPI_CACHE_AVAILABLE = True
except ImportError:
    FASTAPI_CACHE_AVAILABLE = False


def sanitize_redis_url_for_log(redis_url: str) -> str:
    """对 Redis URL 做脱敏，避免密码进入日志。"""
    try:
        parsed = urlsplit(redis_url)
        if parsed.password is None:
            return redis_url

        hostname = parsed.hostname or ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
        sanitized_netloc = f"***@{hostname}" if hostname else "***"
        return urlunsplit(
            (parsed.scheme, sanitized_netloc, parsed.path, parsed.query, parsed.fragment)
        )
    except Exception:
        return "redis://***"


async def init_redis(app: Optional[FastAPI] = None) -> Optional[aioredis.Redis]:
    """初始化 Redis，并在可用时挂到 `app.state.redis`。"""
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        redis = await aioredis.from_url(
            redis_url,
            encoding="utf8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        await redis.ping()

        if FASTAPI_CACHE_AVAILABLE:
            FastAPICache.init(RedisBackend(redis), prefix="xihong-erp:")

        logger.info(
            "[OK] Redis缓存已启用: %s",
            sanitize_redis_url_for_log(redis_url),
        )

        if app is not None:
            app.state.redis = redis

        return redis
    except Exception as exc:
        logger.warning("[SKIP] Redis连接失败，缓存未启用: %s", exc)
        logger.warning("      系统将继续运行，但无缓存加速")
        logger.warning("      启动Redis: docker run -d -p 6379:6379 redis:alpine")
        return None


async def get_redis_client(app: FastAPI) -> Optional[aioredis.Redis]:
    """获取绑定到 FastAPI 应用状态上的 Redis 客户端。"""
    return getattr(app.state, "redis", None)


async def clear_cache(pattern: str = "*", app: Optional[FastAPI] = None):
    """按模式删除缓存 key。"""
    try:
        if app and hasattr(app.state, "redis"):
            redis = app.state.redis
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
                logger.info("[Cache] 清除 %s 个缓存: %s", len(keys), pattern)
        else:
            logger.debug("[Cache] Redis未启用，跳过清除缓存")
    except Exception as exc:
        logger.error("[Cache] 清除缓存失败: %s", exc)
