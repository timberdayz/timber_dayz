#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证限流器存储访问

v4.19.5 新增：验证限流器存储是否正确访问
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.middleware.rate_limiter import limiter
from backend.utils.config import get_settings

print("=" * 50)
print("验证限流器存储访问")
print("=" * 50)

settings = get_settings()
print(f"\n[配置] 存储URI: {settings.rate_limit_storage_uri}")
print(f"[配置] Redis URL: {settings.REDIS_URL}")
print(f"[配置] Redis 启用: {settings.REDIS_ENABLED}")

print(f"\n[限流器] 启用: {limiter.enabled}")

# 检查存储访问
print("\n[测试] 检查存储访问方式...")
storage = None
access_methods = []

try:
    if hasattr(limiter, 'storage'):
        storage = limiter.storage
        access_methods.append("limiter.storage")
except Exception as e:
    pass

try:
    if hasattr(limiter, '_storage_backend'):
        storage = limiter._storage_backend
        access_methods.append("limiter._storage_backend")
except Exception as e:
    pass

try:
    if hasattr(limiter, 'storage_backend'):
        storage = limiter.storage_backend
        access_methods.append("limiter.storage_backend")
except Exception as e:
    pass

if storage:
    print(f"[OK] 存储访问成功，使用方法: {', '.join(access_methods)}")
    print(f"  存储类型: {type(storage).__name__}")
    
    # 检查存储方法
    methods = []
    if hasattr(storage, "get"):
        methods.append("get")
    if hasattr(storage, "set"):
        methods.append("set")
    if hasattr(storage, "incr"):
        methods.append("incr")
    if hasattr(storage, "_storage"):
        methods.append("_storage (内存)")
    
    if methods:
        print(f"  可用方法: {', '.join(methods)}")
else:
    print("[WARN] 无法访问存储（可能使用其他方式）")

print("\n[完成] 验证完成")

