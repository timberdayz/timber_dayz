"""
C类数据缓存工具

实现C类数据的缓存策略：
- 健康度评分缓存（5分钟）
- 达成率缓存（1分钟）
- 排名数据缓存（5分钟）

缓存失效机制：
- 数据更新时自动失效缓存
- 支持手动刷新缓存
- 监控缓存命中率（日志记录）
"""

import json
import hashlib
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 尝试导入Redis（同步版本）
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None


class CClassCache:
    """C类数据缓存管理器"""
    
    # 缓存过期时间（秒）
    CACHE_TTL = {
        "health_score": 300,  # 5分钟
        "achievement_rate": 60,  # 1分钟
        "ranking": 300,  # 5分钟
    }
    
    # 缓存前缀
    CACHE_PREFIX = "c_class:"
    
    def __init__(self, redis_client=None, redis_url: Optional[str] = None):
        """
        初始化缓存管理器
        
        Args:
            redis_client: Redis客户端（可选，如果为None则尝试连接Redis或使用内存缓存）
            redis_url: Redis连接URL（可选，如果redis_client为None且redis_url提供，则尝试连接）
        """
        self.redis_client = redis_client
        self.memory_cache = {}  # 内存缓存（Redis不可用时的降级方案）
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
        
        # 如果未提供redis_client但提供了redis_url，尝试连接
        if self.redis_client is None and redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                self.redis_client.ping()  # 测试连接
                logger.info(f"[Cache] Redis连接成功: {redis_url}")
            except Exception as e:
                logger.warning(f"[Cache] Redis连接失败，使用内存缓存: {e}")
                self.redis_client = None
    
    def _generate_cache_key(
        self,
        cache_type: str,
        **kwargs
    ) -> str:
        """
        生成缓存key
        
        Args:
            cache_type: 缓存类型（health_score/achievement_rate/ranking）
            **kwargs: 查询参数
            
        Returns:
            缓存key字符串
        """
        # 将参数排序后序列化，生成唯一key
        params_str = json.dumps(kwargs, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:16]
        return f"{self.CACHE_PREFIX}{cache_type}:{params_hash}"
    
    def get(
        self,
        cache_type: str,
        **kwargs
    ) -> Optional[Any]:
        """
        获取缓存数据（同步版本）
        
        Args:
            cache_type: 缓存类型
            **kwargs: 查询参数
            
        Returns:
            缓存数据或None
        """
        cache_key = self._generate_cache_key(cache_type, **kwargs)
        
        try:
            if self.redis_client:
                # 使用Redis缓存（同步）
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    self.cache_stats["hits"] += 1
                    logger.debug(f"[Cache] 缓存命中: {cache_key}")
                    return json.loads(cached_data)
                else:
                    self.cache_stats["misses"] += 1
                    logger.debug(f"[Cache] 缓存未命中: {cache_key}")
                    return None
            else:
                # 使用内存缓存
                if cache_key in self.memory_cache:
                    cached_item = self.memory_cache[cache_key]
                    # 检查是否过期
                    if datetime.now() < cached_item["expires_at"]:
                        self.cache_stats["hits"] += 1
                        logger.debug(f"[Cache] 内存缓存命中: {cache_key}")
                        return cached_item["data"]
                    else:
                        # 过期，删除
                        del self.memory_cache[cache_key]
                        self.cache_stats["misses"] += 1
                        logger.debug(f"[Cache] 内存缓存过期: {cache_key}")
                        return None
                else:
                    self.cache_stats["misses"] += 1
                    logger.debug(f"[Cache] 内存缓存未命中: {cache_key}")
                    return None
        except Exception as e:
            logger.warning(f"[Cache] 获取缓存失败: {e}")
            self.cache_stats["misses"] += 1
            return None
    
    def set(
        self,
        cache_type: str,
        data: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        设置缓存数据（同步版本）
        
        Args:
            cache_type: 缓存类型
            data: 要缓存的数据
            ttl: 过期时间（秒），如果为None则使用默认TTL
            **kwargs: 查询参数
            
        Returns:
            是否设置成功
        """
        cache_key = self._generate_cache_key(cache_type, **kwargs)
        
        if ttl is None:
            ttl = self.CACHE_TTL.get(cache_type, 300)
        
        try:
            if self.redis_client:
                # 使用Redis缓存（同步）
                self.redis_client.setex(
                    cache_key,
                    ttl,
                    json.dumps(data, default=str)
                )
                self.cache_stats["sets"] += 1
                logger.debug(f"[Cache] 设置Redis缓存: {cache_key}, TTL={ttl}s")
                return True
            else:
                # 使用内存缓存
                self.memory_cache[cache_key] = {
                    "data": data,
                    "expires_at": datetime.now() + timedelta(seconds=ttl)
                }
                self.cache_stats["sets"] += 1
                logger.debug(f"[Cache] 设置内存缓存: {cache_key}, TTL={ttl}s")
                return True
        except Exception as e:
            logger.warning(f"[Cache] 设置缓存失败: {e}")
            return False
    
    def delete(
        self,
        cache_type: str,
        **kwargs
    ) -> bool:
        """
        删除缓存数据（同步版本）
        
        Args:
            cache_type: 缓存类型
            **kwargs: 查询参数
            
        Returns:
            是否删除成功
        """
        cache_key = self._generate_cache_key(cache_type, **kwargs)
        
        try:
            if self.redis_client:
                # 删除Redis缓存（同步）
                self.redis_client.delete(cache_key)
                self.cache_stats["deletes"] += 1
                logger.debug(f"[Cache] 删除Redis缓存: {cache_key}")
                return True
            else:
                # 删除内存缓存
                if cache_key in self.memory_cache:
                    del self.memory_cache[cache_key]
                    self.cache_stats["deletes"] += 1
                    logger.debug(f"[Cache] 删除内存缓存: {cache_key}")
                    return True
                return False
        except Exception as e:
            logger.warning(f"[Cache] 删除缓存失败: {e}")
            return False
    
    def clear_by_type(
        self,
        cache_type: str
    ) -> int:
        """
        清除指定类型的所有缓存（同步版本）
        
        Args:
            cache_type: 缓存类型
            
        Returns:
            清除的缓存数量
        """
        pattern = f"{self.CACHE_PREFIX}{cache_type}:*"
        count = 0
        
        try:
            if self.redis_client:
                # 清除Redis缓存（同步）
                keys = self.redis_client.keys(pattern)
                if keys:
                    count = self.redis_client.delete(*keys)
                    logger.info(f"[Cache] 清除Redis缓存: {pattern}, 数量={count}")
            else:
                # 清除内存缓存
                keys_to_delete = [
                    key for key in self.memory_cache.keys()
                    if key.startswith(f"{self.CACHE_PREFIX}{cache_type}:")
                ]
                for key in keys_to_delete:
                    del self.memory_cache[key]
                count = len(keys_to_delete)
                logger.info(f"[Cache] 清除内存缓存: {pattern}, 数量={count}")
        except Exception as e:
            logger.warning(f"[Cache] 清除缓存失败: {e}")
        
        return count
    
    def clear_all(self) -> int:
        """
        清除所有C类数据缓存（同步版本）
        
        Returns:
            清除的缓存数量
        """
        pattern = f"{self.CACHE_PREFIX}*"
        count = 0
        
        try:
            if self.redis_client:
                # 清除Redis缓存（同步）
                keys = self.redis_client.keys(pattern)
                if keys:
                    count = self.redis_client.delete(*keys)
                    logger.info(f"[Cache] 清除所有Redis缓存: {pattern}, 数量={count}")
            else:
                # 清除内存缓存
                keys_to_delete = [
                    key for key in self.memory_cache.keys()
                    if key.startswith(self.CACHE_PREFIX)
                ]
                for key in keys_to_delete:
                    del self.memory_cache[key]
                count = len(keys_to_delete)
                logger.info(f"[Cache] 清除所有内存缓存: {pattern}, 数量={count}")
        except Exception as e:
            logger.warning(f"[Cache] 清除所有缓存失败: {e}")
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (
            self.cache_stats["hits"] / total_requests * 100
            if total_requests > 0
            else 0
        )
        
        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "sets": self.cache_stats["sets"],
            "deletes": self.cache_stats["deletes"],
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests,
            "cache_backend": "redis" if self.redis_client else "memory"
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }


# 全局缓存实例（延迟初始化）
_cache_instance: Optional[CClassCache] = None


def get_c_class_cache(redis_client=None, redis_url: Optional[str] = None) -> CClassCache:
    """
    获取C类数据缓存实例（单例模式）
    
    Args:
        redis_client: Redis客户端（可选）
        redis_url: Redis连接URL（可选，如果redis_client为None且redis_url提供，则尝试连接）
        
    Returns:
        CClassCache实例
    """
    global _cache_instance
    
    if _cache_instance is None:
        # 如果没有提供redis_url，尝试从环境变量读取
        if redis_url is None:
            import os
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        _cache_instance = CClassCache(redis_client=redis_client, redis_url=redis_url)
        logger.info("[Cache] C类数据缓存管理器已初始化")
    
    return _cache_instance

