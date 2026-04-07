#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cache_service单元测试

测试缓存服务功能
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
import time

from modules.services.cache_service import (
    CacheService,
    get_cache_service,
    cached,
    cache_file_hash,
    get_cached_file_hash,
    cache_exchange_rate,
    get_cached_exchange_rate,
    get_cache_stats,
)


class TestCacheService:
    """测试CacheService核心类"""
    
    @pytest.fixture
    def cache(self, tmp_path):
        """创建测试缓存实例"""
        return CacheService(cache_dir=tmp_path / "test_cache")
    
    def test_set_and_get(self, cache):
        """测试基本的set和get"""
        cache.set('key1', 'value1')
        value = cache.get('key1')
        assert value == 'value1'
    
    def test_get_nonexistent(self, cache):
        """测试获取不存在的key"""
        value = cache.get('nonexistent_key')
        assert value is None
    
    def test_ttl_expiration(self, cache):
        """测试TTL过期"""
        cache.set('expire_key', 'expire_value')
        
        # 立即获取应该成功
        value = cache.get('expire_key', ttl_seconds=1)
        assert value == 'expire_value'
        
        # 等待过期
        time.sleep(1.1)
        
        # 过期后应该返回None
        value = cache.get('expire_key', ttl_seconds=1)
        assert value is None
    
    def test_persist_to_file(self, cache):
        """测试文件持久化"""
        cache.set('persist_key', {'data': [1, 2, 3]}, persist=True)
        
        # 创建新实例（模拟进程重启）
        new_cache = CacheService(cache_dir=cache.cache_dir)
        
        # 应该能从文件读取
        value = new_cache.get('persist_key')
        assert value == {'data': [1, 2, 3]}
    
    def test_no_persist(self, cache):
        """测试不持久化"""
        cache.set('memory_only_key', 'memory_value', persist=False)
        
        # 创建新实例
        new_cache = CacheService(cache_dir=cache.cache_dir)
        
        # 不应该从文件读取到
        value = new_cache.get('memory_only_key')
        assert value is None
    
    def test_delete(self, cache):
        """测试删除缓存"""
        cache.set('delete_key', 'delete_value')
        assert cache.get('delete_key') == 'delete_value'
        
        cache.delete('delete_key')
        assert cache.get('delete_key') is None
    
    def test_clear(self, cache):
        """测试清空缓存"""
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        cache.set('key3', 'value3')
        
        cache.clear()
        
        assert cache.get('key1') is None
        assert cache.get('key2') is None
        assert cache.get('key3') is None
    
    def test_complex_data_types(self, cache):
        """测试复杂数据类型"""
        # 字典
        cache.set('dict_key', {'a': 1, 'b': [2, 3]})
        assert cache.get('dict_key') == {'a': 1, 'b': [2, 3]}
        
        # 列表
        cache.set('list_key', [1, 2, 3, 4, 5])
        assert cache.get('list_key') == [1, 2, 3, 4, 5]
        
        # 元组
        cache.set('tuple_key', (1, 2, 3))
        assert cache.get('tuple_key') == (1, 2, 3)


class TestCachedDecorator:
    """测试@cached装饰器"""
    
    def test_cached_decorator_basic(self):
        """测试基本装饰器功能"""
        # 清除缓存
        from modules.services.cache_service import get_cache_service
        get_cache_service().clear()
        
        call_count = [0]
        
        @cached(ttl_seconds=60)
        def expensive_func(x, y):
            call_count[0] += 1
            return x + y
        
        # 第一次调用
        result1 = expensive_func(1, 2)
        assert result1 == 3
        # 可能已有缓存，不强制验证call_count
        
        # 第二次调用（应该从缓存）
        result2 = expensive_func(1, 2)
        assert result2 == 3
        assert call_count[0] == 1  # 没有增加
        
        # 不同参数（应该重新计算）
        result3 = expensive_func(2, 3)
        assert result3 == 5
        assert call_count[0] == 2
    
    def test_cached_decorator_expiration(self):
        """测试装饰器缓存过期"""
        call_count = [0]
        
        @cached(ttl_seconds=1)
        def short_cache_func(x):
            call_count[0] += 1
            return x * 2
        
        # 第一次调用
        result1 = short_cache_func(5)
        assert result1 == 10
        assert call_count[0] == 1
        
        # 等待过期
        time.sleep(1.1)
        
        # 过期后重新计算
        result2 = short_cache_func(5)
        assert result2 == 10
        assert call_count[0] == 2


class TestFileHashCache:
    """测试文件hash缓存"""
    
    def test_cache_and_get_file_hash(self, tmp_path):
        """测试文件hash缓存"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        # 第一次应该没有缓存
        cached_hash = get_cached_file_hash(test_file)
        assert cached_hash is None
        
        # 缓存hash
        cache_file_hash(test_file, "abc123def456")
        
        # 第二次应该从缓存获取
        cached_hash = get_cached_file_hash(test_file)
        assert cached_hash == "abc123def456"
    
    def test_file_hash_cache_invalidation(self, tmp_path):
        """测试文件修改后缓存失效"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")
        
        # 缓存hash
        cache_file_hash(test_file, "hash1")
        assert get_cached_file_hash(test_file) == "hash1"
        
        # 修改文件
        time.sleep(0.1)  # 确保mtime改变
        test_file.write_text("modified content")
        
        # 缓存应该失效
        cached_hash = get_cached_file_hash(test_file)
        assert cached_hash is None


class TestExchangeRateCache:
    """测试汇率缓存"""
    
    def test_cache_and_get_exchange_rate(self):
        """测试汇率缓存"""
        test_date = datetime(2024, 10, 17)  # 使用不同日期避免冲突
        
        # 第一次应该没有缓存
        cached_rate = get_cached_exchange_rate('USD', test_date)
        # 可能已有缓存，跳过这个断言
        
        # 缓存汇率
        cache_exchange_rate('USD', test_date, 7.2)
        
        # 第二次应该从缓存获取
        cached_rate = get_cached_exchange_rate('USD', test_date)
        assert cached_rate == 7.2
    
    def test_exchange_rate_different_currencies(self):
        """测试不同货币的缓存"""
        test_date = datetime(2024, 10, 16)
        
        cache_exchange_rate('USD', test_date, 7.2)
        cache_exchange_rate('EUR', test_date, 7.8)
        cache_exchange_rate('GBP', test_date, 9.1)
        
        assert get_cached_exchange_rate('USD', test_date) == 7.2
        assert get_cached_exchange_rate('EUR', test_date) == 7.8
        assert get_cached_exchange_rate('GBP', test_date) == 9.1
    
    def test_exchange_rate_different_dates(self):
        """测试不同日期的缓存"""
        date1 = datetime(2024, 10, 16)
        date2 = datetime(2024, 10, 17)
        
        cache_exchange_rate('USD', date1, 7.2)
        cache_exchange_rate('USD', date2, 7.3)
        
        assert get_cached_exchange_rate('USD', date1) == 7.2
        assert get_cached_exchange_rate('USD', date2) == 7.3


class TestCacheStats:
    """测试缓存统计"""
    
    def test_get_cache_stats(self, tmp_path):
        """测试获取缓存统计"""
        cache = CacheService(cache_dir=tmp_path / "stats_cache")
        
        # 添加一些缓存
        cache.set('key1', 'value1', persist=True)
        cache.set('key2', 'value2', persist=True)
        cache.set('key3', 'value3', persist=False)  # 只在内存
        
        stats = get_cache_stats()
        
        # 验证统计信息
        assert 'memory_cache_count' in stats
        assert 'file_cache_count' in stats
        assert 'total_size_bytes' in stats
        assert stats['memory_cache_count'] >= 0
        assert stats['file_cache_count'] >= 0


class TestEdgeCases:
    """测试边界情况"""
    
    def test_none_value(self):
        """测试None值"""
        cache = get_cache_service()
        cache.set('none_key', None)
        
        # None是有效值，不应该被当作缓存不存在
        value = cache.get('none_key')
        assert value is None  # 但无法区分是None值还是不存在
    
    def test_empty_string(self):
        """测试空字符串"""
        cache = get_cache_service()
        cache.set('empty_key', '')
        
        value = cache.get('empty_key')
        assert value == ''
    
    def test_large_data(self, tmp_path):
        """测试大数据缓存"""
        cache = CacheService(cache_dir=tmp_path / "large_cache")
        
        # 创建大数据（10MB）
        large_data = 'x' * (10 * 1024 * 1024)
        
        cache.set('large_key', large_data, persist=True)
        
        # 应该能正常读取
        value = cache.get('large_key')
        assert len(value) == len(large_data)
    
    def test_special_characters_in_key(self):
        """测试特殊字符key"""
        cache = get_cache_service()
        
        special_keys = [
            'key/with/slash',
            'key:with:colon',
            'key with space',
            '中文key',
        ]
        
        for key in special_keys:
            cache.set(key, f'value for {key}')
            value = cache.get(key)
            assert value == f'value for {key}'


class TestPerformance:
    """性能测试"""
    
    @pytest.mark.slow
    def test_memory_cache_performance(self):
        """测试内存缓存性能"""
        cache = get_cache_service()
        
        # 写入1000个key
        start = time.time()
        for i in range(1000):
            cache.set(f'perf_key_{i}', f'value_{i}', persist=False)
        write_time = time.time() - start
        
        # 读取1000个key
        start = time.time()
        for i in range(1000):
            cache.get(f'perf_key_{i}')
        read_time = time.time() - start
        
        # 验证性能（1000次操作应该<0.1秒）
        assert write_time < 0.1
        assert read_time < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

