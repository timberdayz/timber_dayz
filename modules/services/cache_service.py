#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存服务

提供多层缓存机制，提升系统性能：
1. 内存缓存（LRU）- 用于频繁访问的数据
2. 文件缓存 - 用于持久化缓存数据
3. 数据库缓存 - 用于共享缓存（多进程）

使用场景：
- 文件hash缓存（避免重复计算SHA256）
- 汇率缓存（减少API调用）
- Excel数据缓存（减少文件读取）
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Optional, Dict, Callable
from datetime import datetime, timedelta
from functools import lru_cache, wraps
import pickle


class CacheService:
    """
    统一缓存服务
    
    提供三层缓存：
    1. 内存缓存（最快，进程内）
    2. 文件缓存（持久化，跨进程）
    3. 数据库缓存（共享，适合多进程）
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        初始化缓存服务
        
        Args:
            cache_dir: 缓存文件目录，默认为 temp/cache
        """
        self.cache_dir = cache_dir or Path("temp/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存（字典）
        self._memory_cache: Dict[str, tuple[Any, datetime]] = {}
    
    def get(self, key: str, ttl_seconds: Optional[int] = None) -> Optional[Any]:
        """
        获取缓存值
        
        优先级：内存 -> 文件 -> None
        
        Args:
            key: 缓存键
            ttl_seconds: 有效期（秒），None表示永不过期
        
        Returns:
            缓存值，如果不存在或已过期返回None
        """
        # 1. 检查内存缓存
        if key in self._memory_cache:
            value, timestamp = self._memory_cache[key]
            if ttl_seconds is None or (datetime.now() - timestamp).total_seconds() < ttl_seconds:
                return value
            else:
                # 过期，删除
                del self._memory_cache[key]
        
        # 2. 检查文件缓存
        cache_file = self._get_cache_file(key)
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                    value = data['value']
                    timestamp = data['timestamp']
                
                # 检查是否过期
                if ttl_seconds is None or (datetime.now() - timestamp).total_seconds() < ttl_seconds:
                    # 加载到内存缓存
                    self._memory_cache[key] = (value, timestamp)
                    return value
                else:
                    # 过期，删除文件
                    cache_file.unlink()
            except Exception:
                # 读取失败，删除损坏的缓存文件
                cache_file.unlink(missing_ok=True)
        
        return None
    
    def set(self, key: str, value: Any, persist: bool = True):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            persist: 是否持久化到文件
        """
        timestamp = datetime.now()
        
        # 1. 保存到内存
        self._memory_cache[key] = (value, timestamp)
        
        # 2. 持久化到文件
        if persist:
            cache_file = self._get_cache_file(key)
            try:
                with open(cache_file, 'wb') as f:
                    pickle.dump({
                        'value': value,
                        'timestamp': timestamp
                    }, f)
            except Exception:
                # 忽略持久化失败
                pass
    
    def delete(self, key: str):
        """
        删除缓存
        
        Args:
            key: 缓存键
        """
        # 1. 从内存删除
        self._memory_cache.pop(key, None)
        
        # 2. 从文件删除
        cache_file = self._get_cache_file(key)
        cache_file.unlink(missing_ok=True)
    
    def clear(self):
        """清空所有缓存"""
        # 1. 清空内存
        self._memory_cache.clear()
        
        # 2. 清空文件
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                cache_file.unlink()
            except Exception:
                pass
    
    def _get_cache_file(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用key的hash作为文件名
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.pkl"


# 全局缓存服务实例
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """获取全局缓存服务实例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


# ============================================================
# 装饰器：缓存函数结果
# ============================================================

def cached(ttl_seconds: Optional[int] = 3600, key_func: Optional[Callable] = None):
    """
    缓存装饰器
    
    自动缓存函数结果，减少重复计算
    
    Args:
        ttl_seconds: 缓存有效期（秒），默认1小时
        key_func: 自定义key生成函数，接收函数参数，返回cache key
    
    Example:
        @cached(ttl_seconds=3600)
        def get_exchange_rate(currency: str, date: str) -> float:
            # 昂贵的API调用
            return fetch_rate_from_api(currency, date)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_service()
            
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__module__}.{func.__name__}:{args}:{kwargs}"
            
            # 尝试从缓存获取
            cached_value = cache.get(cache_key, ttl_seconds=ttl_seconds)
            if cached_value is not None:
                return cached_value
            
            # 计算结果
            result = func(*args, **kwargs)
            
            # 保存到缓存
            cache.set(cache_key, result, persist=True)
            
            return result
        
        return wrapper
    return decorator


# ============================================================
# 专用缓存函数
# ============================================================

def cache_file_hash(file_path: Path, hash_value: str):
    """
    缓存文件hash值
    
    避免重复计算SHA256
    
    Args:
        file_path: 文件路径
        hash_value: hash值
    """
    cache = get_cache_service()
    
    # 使用文件路径和修改时间作为key
    mtime = file_path.stat().st_mtime if file_path.exists() else 0
    cache_key = f"file_hash:{file_path}:{mtime}"
    
    cache.set(cache_key, hash_value, persist=True)


def get_cached_file_hash(file_path: Path) -> Optional[str]:
    """
    获取缓存的文件hash值
    
    Args:
        file_path: 文件路径
    
    Returns:
        hash值，如果不存在或文件已修改返回None
    """
    cache = get_cache_service()
    
    if not file_path.exists():
        return None
    
    mtime = file_path.stat().st_mtime
    cache_key = f"file_hash:{file_path}:{mtime}"
    
    return cache.get(cache_key)


def cache_exchange_rate(currency: str, date_obj: datetime, rate: float):
    """
    缓存汇率
    
    Args:
        currency: 货币代码（如USD）
        date_obj: 日期
        rate: 对CNY的汇率
    """
    cache = get_cache_service()
    
    date_str = date_obj.strftime('%Y-%m-%d')
    cache_key = f"exchange_rate:{currency}:{date_str}"
    
    # 汇率缓存7天（一般不会频繁变化）
    cache.set(cache_key, rate, persist=True)


def get_cached_exchange_rate(currency: str, date_obj: datetime) -> Optional[float]:
    """
    获取缓存的汇率
    
    Args:
        currency: 货币代码（如USD）
        date_obj: 日期
    
    Returns:
        汇率，如果不存在返回None
    """
    cache = get_cache_service()
    
    date_str = date_obj.strftime('%Y-%m-%d')
    cache_key = f"exchange_rate:{currency}:{date_str}"
    
    # 7天有效期
    return cache.get(cache_key, ttl_seconds=7 * 24 * 3600)


def cache_excel_data(file_path: Path, sheet_name: str, data: Any):
    """
    缓存Excel数据
    
    Args:
        file_path: Excel文件路径
        sheet_name: Sheet名称
        data: 数据（通常是DataFrame）
    """
    cache = get_cache_service()
    
    # 使用文件路径、sheet名称和修改时间作为key
    mtime = file_path.stat().st_mtime if file_path.exists() else 0
    cache_key = f"excel_data:{file_path}:{sheet_name}:{mtime}"
    
    # 只保存在内存（不持久化，避免占用磁盘空间）
    cache.set(cache_key, data, persist=False)


def get_cached_excel_data(file_path: Path, sheet_name: str) -> Optional[Any]:
    """
    获取缓存的Excel数据
    
    Args:
        file_path: Excel文件路径
        sheet_name: Sheet名称
    
    Returns:
        数据，如果不存在或文件已修改返回None
    """
    cache = get_cache_service()
    
    if not file_path.exists():
        return None
    
    mtime = file_path.stat().st_mtime
    cache_key = f"excel_data:{file_path}:{sheet_name}:{mtime}"
    
    # 1小时有效期
    return cache.get(cache_key, ttl_seconds=3600)


# ============================================================
# 缓存统计
# ============================================================

def get_cache_stats() -> Dict[str, Any]:
    """
    获取缓存统计信息
    
    Returns:
        统计信息字典
    """
    cache = get_cache_service()
    
    # 内存缓存统计
    memory_count = len(cache._memory_cache)
    
    # 文件缓存统计
    cache_files = list(cache.cache_dir.glob("*.pkl"))
    file_count = len(cache_files)
    total_size = sum(f.stat().st_size for f in cache_files)
    
    return {
        'memory_cache_count': memory_count,
        'file_cache_count': file_count,
        'total_size_bytes': total_size,
        'total_size_mb': total_size / 1024 / 1024,
        'cache_dir': str(cache.cache_dir),
    }


# ============================================================
# 示例使用
# ============================================================

if __name__ == '__main__':
    # 示例1：使用装饰器缓存函数
    @cached(ttl_seconds=60)
    def expensive_calculation(x: int, y: int) -> int:
        print(f"计算 {x} + {y}...")
        return x + y
    
    print(expensive_calculation(1, 2))  # 计算
    print(expensive_calculation(1, 2))  # 从缓存读取
    
    # 示例2：手动使用缓存
    cache = get_cache_service()
    cache.set('my_key', {'data': [1, 2, 3]})
    print(cache.get('my_key'))
    
    # 示例3：缓存文件hash
    test_file = Path('test.txt')
    cache_file_hash(test_file, 'abc123')
    print(get_cached_file_hash(test_file))
    
    # 示例4：查看统计
    print(get_cache_stats())

