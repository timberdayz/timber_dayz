#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 Redis 缓存服务（Phase 3）

功能：
1. 统一的缓存键命名规则
2. 缓存读写方法
3. 缓存装饰器
4. 缓存失效机制
5. 缓存统计和监控

使用场景：
- 账号列表（`/api/accounts`）
- 统计数据（`/api/accounts/stats`）
- 组件版本列表（`/api/component-versions`）
- 其他频繁查询的数据
"""

import json
import hashlib
from typing import Optional, Any, Dict, Callable, List
from datetime import datetime, timedelta
from functools import wraps
import os

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 尝试导入Redis（异步版本）
try:
    from redis import asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None


class CacheService:
    """统一 Redis 缓存服务"""
    
    # 缓存键前缀
    CACHE_PREFIX = "xihong_erp:"
    
    # 默认缓存过期时间（秒）
    DEFAULT_TTL = {
        "accounts_list": 300,  # 5分钟
        "accounts_stats": 60,  # 1分钟
        "component_versions": 300,  # 5分钟
        "default": 300,  # 5分钟
    }
    
    def __init__(self, redis_client: Optional[aioredis.Redis] = None, redis_url: Optional[str] = None):
        """
        初始化缓存服务
        
        Args:
            redis_client: Redis客户端（可选，如果为None则尝试连接Redis）
            redis_url: Redis连接URL（可选，如果redis_client为None且redis_url提供，则尝试连接）
        """
        self.redis_client = redis_client
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }
        
        # 如果未提供redis_client但提供了redis_url，尝试连接
        if self.redis_client is None and redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = aioredis.from_url(
                    redis_url,
                    encoding="utf8",
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                logger.info(f"[Cache] Redis连接成功: {redis_url}")
            except Exception as e:
                logger.warning(f"[Cache] Redis连接失败，缓存未启用: {e}")
                self.redis_client = None
        elif self.redis_client is None and REDIS_AVAILABLE:
            # 尝试从环境变量读取Redis配置
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            try:
                self.redis_client = aioredis.from_url(
                    redis_url,
                    encoding="utf8",
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                logger.info(f"[Cache] Redis连接成功: {redis_url}")
            except Exception as e:
                logger.warning(f"[Cache] Redis连接失败，缓存未启用: {e}")
                self.redis_client = None
    
    def _generate_cache_key(
        self,
        cache_type: str,
        **kwargs
    ) -> str:
        """
        生成缓存key
        
        规则：
        - 使用统一的键前缀：`xihong_erp:{cache_type}:{hash}`
        - 包含版本号或时间戳（用于缓存失效）
        - 支持按用户、平台等维度缓存
        
        Args:
            cache_type: 缓存类型（accounts_list/accounts_stats/component_versions等）
            **kwargs: 查询参数（用于生成唯一key）
            
        Returns:
            缓存key字符串
        """
        # 将参数排序后序列化，生成唯一key
        if kwargs:
            params_str = json.dumps(kwargs, sort_keys=True, default=str)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:16]
            return f"{self.CACHE_PREFIX}{cache_type}:{params_hash}"
        else:
            return f"{self.CACHE_PREFIX}{cache_type}"
    
    async def get(
        self,
        cache_type: str,
        **kwargs
    ) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            cache_type: 缓存类型
            **kwargs: 查询参数
            
        Returns:
            缓存数据或None（未命中）
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._generate_cache_key(cache_type, **kwargs)
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                self.cache_stats["hits"] += 1
                logger.debug(f"[Cache] 缓存命中: {cache_key}")
                return json.loads(cached_data)
            else:
                self.cache_stats["misses"] += 1
                logger.debug(f"[Cache] 缓存未命中: {cache_key}")
                return None
        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.warning(f"[Cache] 获取缓存失败: {e}")
            return None
    
    async def set(
        self,
        cache_type: str,
        data: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        设置缓存数据
        
        Args:
            cache_type: 缓存类型
            data: 要缓存的数据（必须是JSON可序列化的）
            ttl: 过期时间（秒），如果为None则使用默认TTL
            **kwargs: 查询参数
            
        Returns:
            是否设置成功
        """
        if not self.redis_client:
            return False
        
        try:
            cache_key = self._generate_cache_key(cache_type, **kwargs)
            
            # 确定TTL
            if ttl is None:
                ttl = self.DEFAULT_TTL.get(cache_type, self.DEFAULT_TTL["default"])
            
            # 序列化数据
            data_str = json.dumps(data, default=str, ensure_ascii=False)
            
            # 设置缓存
            await self.redis_client.setex(cache_key, ttl, data_str)
            self.cache_stats["sets"] += 1
            logger.debug(f"[Cache] 缓存设置: {cache_key} (TTL={ttl}s)")
            return True
        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.warning(f"[Cache] 设置缓存失败: {e}")
            return False
    
    async def delete(
        self,
        cache_type: str,
        **kwargs
    ) -> bool:
        """
        删除缓存数据
        
        Args:
            cache_type: 缓存类型
            **kwargs: 查询参数
            
        Returns:
            是否删除成功
        """
        if not self.redis_client:
            return False
        
        try:
            cache_key = self._generate_cache_key(cache_type, **kwargs)
            await self.redis_client.delete(cache_key)
            self.cache_stats["deletes"] += 1
            logger.debug(f"[Cache] 缓存删除: {cache_key}")
            return True
        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.warning(f"[Cache] 删除缓存失败: {e}")
            return False
    
    async def delete_pattern(
        self,
        pattern: str
    ) -> int:
        """
        按模式删除缓存数据
        
        Args:
            pattern: 缓存key模式（如 "xihong_erp:accounts:*"）
            
        Returns:
            删除的缓存数量
        """
        if not self.redis_client:
            return 0
        
        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                count = await self.redis_client.delete(*keys)
                self.cache_stats["deletes"] += count
                logger.info(f"[Cache] 删除 {count} 个缓存: {pattern}")
                return count
            return 0
        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.warning(f"[Cache] 按模式删除缓存失败: {e}")
            return 0
    
    async def invalidate(
        self,
        cache_type: str
    ) -> int:
        """
        失效指定类型的所有缓存
        
        Args:
            cache_type: 缓存类型
            
        Returns:
            失效的缓存数量
        """
        pattern = f"{self.CACHE_PREFIX}{cache_type}:*"
        return await self.delete_pattern(pattern)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "sets": self.cache_stats["sets"],
            "deletes": self.cache_stats["deletes"],
            "errors": self.cache_stats["errors"],
            "total_requests": total_requests,
            "hit_rate": round(hit_rate, 2)
        }
    
    def reset_stats(self):
        """重置缓存统计"""
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }


# 全局缓存服务实例（延迟初始化）
_cache_service: Optional[CacheService] = None


def get_cache_service(redis_client: Optional[aioredis.Redis] = None) -> CacheService:
    """
    获取缓存服务实例（单例模式）
    
    Args:
        redis_client: Redis客户端（可选，首次调用时初始化）
        
    Returns:
        CacheService实例
    """
    global _cache_service
    
    if _cache_service is None:
        _cache_service = CacheService(redis_client=redis_client)
    
    return _cache_service


def cache_result(
    cache_type: str,
    ttl: Optional[int] = None,
    key_func: Optional[Callable] = None
):
    """
    缓存装饰器
    
    使用示例：
        @cache_result("accounts_list", ttl=300)
        async def get_accounts(platform: str = None):
            # 函数实现
            return accounts
    
    Args:
        cache_type: 缓存类型
        ttl: 过期时间（秒），如果为None则使用默认TTL
        key_func: 自定义缓存键生成函数（可选）
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取缓存服务
            cache_service = get_cache_service()
            
            # 生成缓存key
            if key_func:
                cache_key_params = key_func(*args, **kwargs)
            else:
                # 默认使用kwargs作为缓存key参数
                cache_key_params = kwargs
            
            # 尝试从缓存获取
            cached_data = await cache_service.get(cache_type, **cache_key_params)
            if cached_data is not None:
                return cached_data
            
            # 缓存未命中，执行函数
            result = await func(*args, **kwargs)
            
            # 将结果写入缓存
            await cache_service.set(cache_type, result, ttl=ttl, **cache_key_params)
            
            return result
        
        return wrapper
    return decorator

