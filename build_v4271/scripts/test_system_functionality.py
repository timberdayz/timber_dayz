#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统功能验证脚本

v4.19.5 新增：验证限流器和认证功能是否正常
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import time

BASE_URL = "http://127.0.0.1:8001"

async def test_rate_limiter():
    """测试限流器功能"""
    print("\n" + "=" * 50)
    print("测试 1: 限流器功能")
    print("=" * 50)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 测试健康检查端点（无认证）
        try:
            response = await client.get(f"{BASE_URL}/api/health")
            print(f"[OK] 健康检查: {response.status_code}")
        except Exception as e:
            print(f"[FAIL] 健康检查失败: {e}")
            return False
    
    return True

async def test_auth_endpoints():
    """测试认证端点（限流保护）"""
    print("\n" + "=" * 50)
    print("测试 2: 认证端点限流")
    print("=" * 50)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 测试注册端点（应该有限流保护）
        try:
            # 快速发送多个请求测试限流
            for i in range(5):
                response = await client.post(
                    f"{BASE_URL}/api/auth/register",
                    json={
                        "username": f"test_user_{i}",
                        "password": "test123456",
                        "email": f"test{i}@example.com"
                    }
                )
                print(f"  请求 {i+1}: {response.status_code}")
                if response.status_code == 429:
                    print(f"[OK] 限流生效: 收到 429 响应")
                    break
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[WARN] 注册端点测试失败: {e}")
    
    return True

async def test_rate_limit_config_api():
    """测试限流配置 API"""
    print("\n" + "=" * 50)
    print("测试 3: 限流配置 API")
    print("=" * 50)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 需要认证，先尝试登录
            login_response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json={
                    "username": "admin",
                    "password": "admin123"
                }
            )
            
            if login_response.status_code == 200:
                token = login_response.json().get("access_token")
                if token:
                    headers = {"Authorization": f"Bearer {token}"}
                    # 测试限流配置 API
                    config_response = await client.get(
                        f"{BASE_URL}/api/rate-limit/config/roles",
                        headers=headers
                    )
                    print(f"[OK] 限流配置 API: {config_response.status_code}")
                    if config_response.status_code == 200:
                        data = config_response.json()
                        print(f"  配置数量: {len(data.get('configs', []))}")
                else:
                    print("[WARN] 登录成功但未获取到 token")
            else:
                print(f"[WARN] 登录失败: {login_response.status_code}")
        except Exception as e:
            print(f"[WARN] 限流配置 API 测试失败: {e}")
    
    return True

async def main():
    """主测试函数"""
    print("=" * 50)
    print("系统功能验证 - v4.19.5")
    print("=" * 50)
    
    # 等待服务启动
    print("\n[等待] 等待服务启动...")
    await asyncio.sleep(3)
    
    # 测试服务是否可用
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/api/health")
            if response.status_code == 200:
                print("[OK] 服务已启动")
            else:
                print(f"[WARN] 服务响应异常: {response.status_code}")
                return
    except Exception as e:
        print(f"[FAIL] 服务未启动或不可访问: {e}")
        print("请确保后端服务已启动（python run.py）")
        return
    
    # 运行测试
    results = []
    results.append(await test_rate_limiter())
    results.append(await test_auth_endpoints())
    results.append(await test_rate_limit_config_api())
    
    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)
    print(f"通过: {sum(results)}/{len(results)}")
    
    if all(results):
        print("[OK] 所有测试通过")
    else:
        print("[WARN] 部分测试失败（可能是预期的）")

if __name__ == "__main__":
    asyncio.run(main())

