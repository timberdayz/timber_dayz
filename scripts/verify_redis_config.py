#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证 Redis 配置

v4.19.5 新增：验证 Redis 密码配置是否正确
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 50)
print("验证 Redis 配置 - v4.19.5")
print("=" * 50)

# 1. 检查环境变量
import os
redis_url = os.getenv("REDIS_URL", "")
redis_password = os.getenv("REDIS_PASSWORD", "")

print(f"\n[环境变量] REDIS_URL: {redis_url[:50]}..." if len(redis_url) > 50 else f"\n[环境变量] REDIS_URL: {redis_url}")
print(f"[环境变量] REDIS_PASSWORD: {'已设置' if redis_password else '未设置'}")

# 2. 检查配置类
try:
    from backend.utils.config import get_settings
    settings = get_settings()
    print(f"\n[配置类] REDIS_URL: {settings.REDIS_URL[:50]}..." if len(settings.REDIS_URL) > 50 else f"\n[配置类] REDIS_URL: {settings.REDIS_URL}")
    print(f"[配置类] REDIS_ENABLED: {settings.REDIS_ENABLED}")
except Exception as e:
    print(f"\n[ERROR] 无法加载配置: {e}")

# 3. 测试 Redis 连接
try:
    import redis
    # 从 REDIS_URL 解析密码
    if redis_url.startswith("redis://:"):
        # 格式：redis://:password@host:port/db
        password = redis_url.split("@")[0].replace("redis://:", "")
        host_port = redis_url.split("@")[1].split("/")[0]
        host = host_port.split(":")[0]
        port = int(host_port.split(":")[1]) if ":" in host_port else 6379
    else:
        password = redis_password if redis_password else None
        host = "localhost"
        port = 6379
    
    print(f"\n[测试] 连接 Redis...")
    print(f"  主机: {host}")
    print(f"  端口: {port}")
    print(f"  密码: {'已设置' if password else '无密码'}")
    
    r = redis.Redis(host=host, port=port, password=password, socket_connect_timeout=2)
    result = r.ping()
    r.close()
    
    if result:
        print("[OK] Redis 连接成功！")
    else:
        print("[WARN] Redis 连接返回 False")
        
except redis.exceptions.AuthenticationError as e:
    print(f"[ERROR] Redis 认证失败: {e}")
    print("  请检查密码是否正确")
except redis.exceptions.ConnectionError as e:
    print(f"[ERROR] Redis 连接失败: {e}")
    print("  请检查 Redis 服务是否运行")
except Exception as e:
    print(f"[ERROR] Redis 测试失败: {e}")

print("\n[完成] 验证完成")

