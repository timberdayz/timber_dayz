#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
限流配置服务（Phase 3）

用途：
- 从数据库读取限流配置
- 实现配置缓存机制
- 支持配置热更新

v4.19.4 新增：Phase 3 数据库配置支持
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.db import DimRateLimitConfig
from modules.core.logger import get_logger

logger = get_logger(__name__)


class RateLimitConfigService:
    """
    限流配置服务
    
    功能：
    - 从数据库读取限流配置
    - 配置缓存（减少数据库查询）
    - 配置热更新支持
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化服务
        
        Args:
            db: 数据库会话（异步）
        """
        self.db = db
        self._cache: Optional[Dict[str, Dict[str, str]]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # 缓存5分钟
    
    async def get_rate_limit_tiers(self, force_refresh: bool = False) -> Dict[str, Dict[str, str]]:
        """
        获取限流配置（带缓存）
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            Dict[str, Dict[str, str]]: 限流配置字典
            格式: {
                "admin": {
                    "default": "200/minute",
                    "data_sync": "100/minute",
                    "auth": "20/minute",
                },
                ...
            }
        """
        # 检查缓存是否有效
        if not force_refresh and self._cache is not None and self._cache_timestamp is not None:
            if datetime.utcnow() - self._cache_timestamp < self._cache_ttl:
                logger.debug("[RateLimitConfig] 使用缓存配置")
                return self._cache
        
        # 从数据库读取配置
        logger.info("[RateLimitConfig] 从数据库读取配置")
        configs = await self._load_from_database()
        
        # 更新缓存
        self._cache = configs
        self._cache_timestamp = datetime.utcnow()
        
        return configs
    
    async def _load_from_database(self) -> Dict[str, Dict[str, str]]:
        """
        从数据库加载配置
        
        Returns:
            Dict[str, Dict[str, str]]: 限流配置字典
        """
        try:
            # 查询所有启用的配置
            stmt = select(DimRateLimitConfig).where(
                DimRateLimitConfig.is_active == True
            )
            result = await self.db.execute(stmt)
            configs = result.scalars().all()
            
            # 构建配置字典
            tiers: Dict[str, Dict[str, str]] = {}
            for config in configs:
                role_code = config.role_code
                endpoint_type = config.endpoint_type
                limit_value = config.limit_value
                
                if role_code not in tiers:
                    tiers[role_code] = {}
                
                tiers[role_code][endpoint_type] = limit_value
            
            logger.info(f"[RateLimitConfig] 从数据库加载了 {len(configs)} 条配置")
            return tiers
            
        except Exception as e:
            logger.error(f"[RateLimitConfig] 从数据库加载配置失败: {e}")
            # 返回空字典，让系统使用默认配置
            return {}
    
    async def get_rate_limit_for_role(
        self,
        role_code: str,
        endpoint_type: str = "default",
        force_refresh: bool = False
    ) -> Optional[str]:
        """
        获取指定角色和端点类型的限流值
        
        Args:
            role_code: 角色代码
            endpoint_type: 端点类型（default/data_sync/auth）
            force_refresh: 是否强制刷新缓存
            
        Returns:
            Optional[str]: 限流值（如 "200/minute"），如果不存在则返回 None
        """
        tiers = await self.get_rate_limit_tiers(force_refresh=force_refresh)
        
        if role_code not in tiers:
            return None
        
        role_config = tiers[role_code]
        return role_config.get(endpoint_type)
    
    async def refresh_cache(self):
        """
        刷新缓存
        
        用于配置更新后立即刷新缓存
        """
        logger.info("[RateLimitConfig] 刷新配置缓存")
        self._cache = None
        self._cache_timestamp = None
        await self.get_rate_limit_tiers(force_refresh=True)


# 全局配置服务实例（单例模式）
_config_service: Optional[RateLimitConfigService] = None


def get_config_service(db: AsyncSession) -> RateLimitConfigService:
    """
    获取配置服务实例
    
    Args:
        db: 数据库会话（异步）
        
    Returns:
        RateLimitConfigService: 配置服务实例
    """
    global _config_service
    if _config_service is None:
        _config_service = RateLimitConfigService(db)
    return _config_service

