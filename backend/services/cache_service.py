#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 Redis 缓存服务(Phase 3)

功能:
1. 统一的缓存键命名规则
2. 缓存读写方法
3. 缓存装饰器
4. 缓存失效机制
5. 缓存统计和监控

使用场景:
- 账号列表(`/api/accounts`)
- 统计数据(`/api/accounts/stats`)
- 组件版本列表(`/api/component-versions`)
- 其他频繁查询的数据
"""

import asyncio
import hashlib
import json
import uuid
from typing import Optional, Any, Dict, Callable, List
from datetime import datetime, timedelta
from functools import wraps
import os

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 尝试导入Redis(异步版本)
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
    
    # 默认缓存过期时间(秒)
    DEFAULT_TTL = {
        "accounts_list": 300,  # 5分钟
        "accounts_stats": 60,  # 1分钟
        "component_versions": 300,  # 5分钟
        # Dashboard 业务概览（add-dashboard-redis-cache-performance）
        "dashboard_kpi": 180,
        "dashboard_comparison": 180,
        "dashboard_shop_racing": 180,
        "dashboard_traffic_ranking": 180,
        "dashboard_operational_metrics": 180,
        "dashboard_clearance_ranking": 300,
        "dashboard_inventory_backlog": 300,
        "annual_summary_kpi": 180,  # 年度数据总结 KPI（add-annual-data-summary）
        # add-redis-cache-uncached-endpoints
        "performance_scores": 180,
        "performance_scores_shop": 180,
        "hr_shop_profit_statistics": 300,
        "hr_annual_profit_statistics": 300,
        "annual_summary_by_shop": 180,
        "annual_summary_trend": 180,
        "annual_summary_platform_share": 180,
        "annual_summary_target_completion": 180,
        "expense_summary_monthly": 300,
        "expense_summary_yearly": 300,
        "target_by_month": 180,
        "target_breakdown": 180,
        "default": 300,  # 5分钟
    }
    
    def __init__(self, redis_client: Optional[aioredis.Redis] = None, redis_url: Optional[str] = None):
        """
        初始化缓存服务
        
        Args:
            redis_client: Redis客户端(可选,如果为None则尝试连接Redis)
            redis_url: Redis连接URL(可选,如果redis_client为None且redis_url提供,则尝试连接)
        """
        self.redis_client = redis_client
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }
        self._local_locks: Dict[str, asyncio.Lock] = {}
        self._local_locks_guard = asyncio.Lock()
        
        # 如果未提供redis_client但提供了redis_url,尝试连接
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
                logger.warning(f"[Cache] Redis连接失败,缓存未启用: {e}")
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
                logger.warning(f"[Cache] Redis连接失败,缓存未启用: {e}")
                self.redis_client = None
    
    def _generate_cache_key(
        self,
        cache_type: str,
        **kwargs
    ) -> str:
        """
        生成缓存key
        
        规则:
        - 使用统一的键前缀:`xihong_erp:{cache_type}:{hash}`
        - 包含版本号或时间戳(用于缓存失效)
        - 支持按用户、平台等维度缓存
        
        Args:
            cache_type: 缓存类型(accounts_list/accounts_stats/component_versions等)
            **kwargs: 查询参数(用于生成唯一key)
            
        Returns:
            缓存key字符串
        """
        # 将参数排序后序列化,生成唯一key
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
            缓存数据或None(未命中)
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
            data: 要缓存的数据(必须是JSON可序列化的)
            ttl: 过期时间(秒),如果为None则使用默认TTL
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
    
    async def _get_local_lock(self, lock_key: str) -> asyncio.Lock:
        async with self._local_locks_guard:
            lock = self._local_locks.get(lock_key)
            if lock is None:
                lock = asyncio.Lock()
                self._local_locks[lock_key] = lock
            return lock

    async def _release_singleflight_lock(self, lock_key: str, lock_token: str) -> None:
        if not self.redis_client:
            return
        try:
            current_value = await self.redis_client.get(lock_key)
            if current_value == lock_token:
                await self.redis_client.delete(lock_key)
        except Exception as e:
            logger.debug(f"[Cache] release singleflight lock failed: {e}")

    async def get_or_set_singleflight(
        self,
        cache_type: str,
        producer: Callable[[], Any],
        ttl: Optional[int] = None,
        lock_ttl: int = 15,
        wait_timeout: float = 5.0,
        poll_interval: float = 0.05,
        **kwargs
    ) -> Any:
        cache_key = self._generate_cache_key(cache_type, **kwargs)

        cached_data = await self.get(cache_type, **kwargs)
        if cached_data is not None:
            return cached_data

        if ttl is None:
            ttl = self.DEFAULT_TTL.get(cache_type, self.DEFAULT_TTL["default"])

        if not self.redis_client:
            local_lock = await self._get_local_lock(cache_key)
            async with local_lock:
                cached_data = await self.get(cache_type, **kwargs)
                if cached_data is not None:
                    return cached_data
                produced = await producer()
                await self.set(cache_type, produced, ttl=ttl, **kwargs)
                return produced

        lock_key = f"{cache_key}:lock"
        lock_token = uuid.uuid4().hex

        try:
            lock_acquired = await self.redis_client.set(
                lock_key,
                lock_token,
                ex=lock_ttl,
                nx=True,
            )
        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.warning(f"[Cache] singleflight lock failed, fallback to producer: {e}")
            produced = await producer()
            await self.set(cache_type, produced, ttl=ttl, **kwargs)
            return produced

        if lock_acquired:
            try:
                cached_data = await self.get(cache_type, **kwargs)
                if cached_data is not None:
                    return cached_data
                produced = await producer()
                await self.set(cache_type, produced, ttl=ttl, **kwargs)
                return produced
            finally:
                await self._release_singleflight_lock(lock_key, lock_token)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_timeout
        while loop.time() < deadline:
            await asyncio.sleep(poll_interval)
            cached_data = await self.get(cache_type, **kwargs)
            if cached_data is not None:
                return cached_data
            try:
                if not await self.redis_client.get(lock_key):
                    break
            except Exception:
                break

        produced = await producer()
        await self.set(cache_type, produced, ttl=ttl, **kwargs)
        return produced

    async def delete_pattern(
        self,
        pattern: str
    ) -> int:
        """
        按模式删除缓存数据（使用 SCAN 游标迭代，避免 KEYS O(N) 阻塞）
        
        Args:
            pattern: 缓存key模式(如 "xihong_erp:accounts:*")
            
        Returns:
            删除的缓存数量
        """
        if not self.redis_client:
            return 0
        
        try:
            total_deleted = 0
            batch_size = 100
            keys_batch: List[str] = []
            async for key in self.redis_client.scan_iter(match=pattern, count=100):
                keys_batch.append(key)
                if len(keys_batch) >= batch_size:
                    count = await self.redis_client.delete(*keys_batch)
                    total_deleted += count
                    self.cache_stats["deletes"] += count
                    keys_batch = []
            if keys_batch:
                count = await self.redis_client.delete(*keys_batch)
                total_deleted += count
                self.cache_stats["deletes"] += count
            if total_deleted > 0:
                logger.info(f"[Cache] 删除 {total_deleted} 个缓存: {pattern}")
            return total_deleted
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

    async def invalidate_dashboard_business_overview(self) -> int:
        """
        写时失效：业务概览与年度总结相关 Dashboard 缓存（proposal 约定集中在此执行）。
        在数据同步完成、经营目标/配置更新等事件后调用，确保后续请求命中 DB/Metabase 取得新数据。
        Key 约定：xihong_erp:dashboard_*、xihong_erp:annual_summary_*
        """
        n1 = await self.delete_pattern(f"{self.CACHE_PREFIX}dashboard_*")
        n2 = await self.delete_pattern(f"{self.CACHE_PREFIX}annual_summary_*")
        total = n1 + n2
        if total > 0:
            logger.info(f"[Cache] 写时失效 Dashboard 相关缓存: 共 {total} 个 key")
        return total
    
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


# 全局缓存服务实例(延迟初始化)
_cache_service: Optional[CacheService] = None


def get_cache_service(redis_client: Optional[aioredis.Redis] = None) -> CacheService:
    """
    获取缓存服务实例(单例模式)
    
    Args:
        redis_client: Redis客户端(可选,首次调用时初始化)
        
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
    
    使用示例:
        @cache_result("accounts_list", ttl=300)
        async def get_accounts(platform: str = None):
            # 函数实现
            return accounts
    
    Args:
        cache_type: 缓存类型
        ttl: 过期时间(秒),如果为None则使用默认TTL
        key_func: 自定义缓存键生成函数(可选)
        
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
            
            # 缓存未命中,执行函数
            result = await func(*args, **kwargs)
            
            # 将结果写入缓存
            await cache_service.set(cache_type, result, ttl=ttl, **cache_key_params)
            
            return result
        
        return wrapper
    return decorator


def invalidate_dashboard_cache_sync() -> int:
    """
    写时失效 Dashboard 缓存的同步入口（供 Celery 等同步上下文调用）。
    仅在无事件循环的线程中调用；异步上下文中请直接 await cache.invalidate_dashboard_business_overview()。
    """
    import asyncio
    return asyncio.run(get_cache_service().invalidate_dashboard_business_overview())
