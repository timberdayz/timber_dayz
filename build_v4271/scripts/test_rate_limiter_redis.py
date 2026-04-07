#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试限流器 Redis 存储功能

v4.19.5 新增：验证限流器 Redis 存储是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.middleware.rate_limiter import limiter, check_redis_connection
from backend.utils.config import get_settings
import asyncio

async def test_rate_limiter_redis():
    """测试限流器 Redis 存储"""
    print("=" * 50)
    print("v4.19.5: 测试限流器 Redis 存储")
    print("=" * 50)
    
    settings = get_settings()
    print(f"\n[配置] 限流器存储URI: {settings.rate_limit_storage_uri}")
    print(f"[配置] Redis URL: {settings.REDIS_URL}")
    print(f"[配置] Redis 启用: {settings.REDIS_ENABLED}")
    print(f"[配置] 环境: {settings.ENVIRONMENT}")
    
    print(f"\n[限流器] 启用状态: {limiter.enabled}")
    
    # 检查 Redis 连接
    if settings.rate_limit_storage_uri.startswith("redis://"):
        print("\n[测试] 检查 Redis 连接...")
        redis_ok = await check_redis_connection()
        if redis_ok:
            print("[OK] Redis 连接正常")
        else:
            print("[WARN] Redis 连接失败，将使用内存存储（降级）")
    else:
        print("\n[信息] 使用内存存储（非 Redis）")
    
    print("\n[完成] 测试完成")

if __name__ == "__main__":
    asyncio.run(test_rate_limiter_redis())

