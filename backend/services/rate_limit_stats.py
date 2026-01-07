#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流统计服务

v4.19.2 新增:
- 记录限流事件
- 统计限流触发频率
- 识别异常流量模式
- 提供监控数据

功能:
- 记录每次限流触发事件
- 统计每个 API 的限流触发频率
- 统计每个用户/IP 的限流触发次数
- 识别异常流量模式（如单个 IP 频繁触发）
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import redis.asyncio as redis
import json

from modules.core.logger import get_logger
from backend.utils.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


class RateLimitStatsService:
    """限流统计服务"""
    
    def __init__(self):
        self._redis_client: Optional[redis.Redis] = None
        self._local_stats: Dict[str, Any] = defaultdict(lambda: defaultdict(int))
        self._stats_key_prefix = "xihong_erp:rate_limit_stats"
        self._event_key_prefix = "xihong_erp:rate_limit_events"
        self._max_events_per_key = 1000  # 每个键最多保留 1000 条事件
        self._event_expire_seconds = 86400  # 事件过期时间：24 小时
    
    def _get_redis_client(self) -> Optional[redis.Redis]:
        """获取 Redis 客户端"""
        if self._redis_client is None:
            try:
                redis_url = settings.REDIS_URL
                self._redis_client = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.warning(f"[RateLimitStats] Redis 连接失败: {e}")
                return None
        return self._redis_client
    
    async def record_rate_limit_event(
        self,
        rate_limit_key: str,
        path: str,
        method: str,
        detail: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        记录限流事件
        
        Args:
            rate_limit_key: 限流键（user:xxx 或 ip:xxx）
            path: API 路径
            method: HTTP 方法
            detail: 限流详情
            ip_address: IP 地址（可选）
            user_agent: User-Agent（可选）
        """
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "rate_limit_key": rate_limit_key,
            "path": path,
            "method": method,
            "detail": detail,
            "ip_address": ip_address,
            "user_agent": user_agent[:200] if user_agent else None  # 截断 User-Agent
        }
        
        redis_client = self._get_redis_client()
        if redis_client:
            try:
                # 记录事件到 Redis List
                event_list_key = f"{self._event_key_prefix}:{datetime.utcnow().strftime('%Y-%m-%d')}"
                await redis_client.lpush(event_list_key, json.dumps(event))
                
                # 限制列表长度
                await redis_client.ltrim(event_list_key, 0, self._max_events_per_key - 1)
                
                # 设置过期时间
                await redis_client.expire(event_list_key, self._event_expire_seconds)
                
                # 更新统计计数
                stats_key = f"{self._stats_key_prefix}:counts:{datetime.utcnow().strftime('%Y-%m-%d')}"
                await redis_client.hincrby(stats_key, f"total", 1)
                await redis_client.hincrby(stats_key, f"path:{path}", 1)
                await redis_client.hincrby(stats_key, f"key:{rate_limit_key}", 1)
                await redis_client.expire(stats_key, self._event_expire_seconds)
                
            except Exception as e:
                logger.warning(f"[RateLimitStats] 记录限流事件到 Redis 失败: {e}")
                # 降级到本地统计
                self._record_local_event(event)
        else:
            # Redis 不可用，使用本地统计
            self._record_local_event(event)
    
    def _record_local_event(self, event: Dict[str, Any]) -> None:
        """记录事件到本地内存（降级方案）"""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        self._local_stats[today]["total"] += 1
        self._local_stats[today][f"path:{event['path']}"] += 1
        self._local_stats[today][f"key:{event['rate_limit_key']}"] += 1
    
    async def get_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取限流统计数据
        
        Args:
            date: 日期（YYYY-MM-DD 格式），默认为今天
            
        Returns:
            Dict: 统计数据
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')
        
        redis_client = self._get_redis_client()
        if redis_client:
            try:
                stats_key = f"{self._stats_key_prefix}:counts:{date}"
                stats = await redis_client.hgetall(stats_key)
                
                # 解析统计数据
                result = {
                    "date": date,
                    "total": int(stats.get("total", 0)),
                    "by_path": {},
                    "by_key": {},
                    "source": "redis"
                }
                
                for key, value in stats.items():
                    if key.startswith("path:"):
                        result["by_path"][key.replace("path:", "")] = int(value)
                    elif key.startswith("key:"):
                        result["by_key"][key.replace("key:", "")] = int(value)
                
                return result
            except Exception as e:
                logger.warning(f"[RateLimitStats] 获取 Redis 统计失败: {e}")
        
        # 降级到本地统计
        local_stats = self._local_stats.get(date, {})
        result = {
            "date": date,
            "total": local_stats.get("total", 0),
            "by_path": {},
            "by_key": {},
            "source": "local"
        }
        
        for key, value in local_stats.items():
            if key.startswith("path:"):
                result["by_path"][key.replace("path:", "")] = value
            elif key.startswith("key:"):
                result["by_key"][key.replace("key:", "")] = value
        
        return result
    
    async def get_recent_events(
        self,
        date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取最近的限流事件
        
        Args:
            date: 日期（YYYY-MM-DD 格式），默认为今天
            limit: 返回数量限制
            
        Returns:
            List: 限流事件列表
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')
        
        redis_client = self._get_redis_client()
        if redis_client:
            try:
                event_list_key = f"{self._event_key_prefix}:{date}"
                events_json = await redis_client.lrange(event_list_key, 0, limit - 1)
                return [json.loads(e) for e in events_json]
            except Exception as e:
                logger.warning(f"[RateLimitStats] 获取 Redis 事件列表失败: {e}")
        
        return []
    
    async def check_anomalies(self, threshold: int = 100) -> List[Dict[str, Any]]:
        """
        检查异常流量模式
        
        Args:
            threshold: 触发告警的阈值（单个 key 在一天内的限流次数）
            
        Returns:
            List: 异常列表
        """
        stats = await self.get_stats()
        anomalies = []
        
        # 检查单个 key 的限流次数是否超过阈值
        for key, count in stats.get("by_key", {}).items():
            if count >= threshold:
                anomalies.append({
                    "type": "high_rate_limit_count",
                    "key": key,
                    "count": count,
                    "threshold": threshold,
                    "severity": "warning" if count < threshold * 2 else "critical"
                })
        
        # 检查单个 API 的限流次数
        for path, count in stats.get("by_path", {}).items():
            if count >= threshold * 2:  # API 级别使用更高的阈值
                anomalies.append({
                    "type": "high_api_rate_limit",
                    "path": path,
                    "count": count,
                    "threshold": threshold * 2,
                    "severity": "warning" if count < threshold * 4 else "critical"
                })
        
        return anomalies
    
    async def clear_stats(self, date: Optional[str] = None) -> None:
        """
        清除统计数据
        
        Args:
            date: 日期（YYYY-MM-DD 格式），默认为今天
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')
        
        redis_client = self._get_redis_client()
        if redis_client:
            try:
                stats_key = f"{self._stats_key_prefix}:counts:{date}"
                event_list_key = f"{self._event_key_prefix}:{date}"
                await redis_client.delete(stats_key, event_list_key)
            except Exception as e:
                logger.warning(f"[RateLimitStats] 清除 Redis 统计失败: {e}")
        
        # 清除本地统计
        if date in self._local_stats:
            del self._local_stats[date]


# 单例实例
_rate_limit_stats_service: Optional[RateLimitStatsService] = None


def get_rate_limit_stats_service() -> RateLimitStatsService:
    """获取限流统计服务单例"""
    global _rate_limit_stats_service
    if _rate_limit_stats_service is None:
        _rate_limit_stats_service = RateLimitStatsService()
    return _rate_limit_stats_service

