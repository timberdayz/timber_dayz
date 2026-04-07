#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试物化视图刷新API
验证API端点是否正确注册和工作
"""

import sys
from pathlib import Path
import requests
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_mv_refresh_api():
    """测试物化视图刷新API"""
    base_url = "http://localhost:8001/api"
    
    print("=" * 70)
    print("测试物化视图刷新API")
    print("=" * 70)
    
    # 1. 测试API端点是否存在
    print("\n[1] 测试API端点是否存在...")
    try:
        # ⭐ 修复：禁用代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.post(
            f"{base_url}/mv/refresh-all",
            json={},
            headers={"Content-Type": "application/json"},
            timeout=120,  # 刷新可能需要较长时间
            proxies=proxies  # 禁用代理
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 404:
            print("  [ERROR] API端点不存在（404）")
            print("  原因: 后端服务可能没有重启，新路由未生效")
            print("  解决方案: 请重启后端服务（python run.py）")
            return False
        elif response.status_code == 200:
            print("  [OK] API端点存在")
            data = response.json()
            print(f"  响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"  [WARNING] 意外的状态码: {response.status_code}")
            print(f"  响应: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("  [ERROR] 无法连接到后端服务")
        print("  原因: 后端服务可能未运行")
        print("  解决方案: 请启动后端服务（python run.py）")
        return False
    except Exception as e:
        print(f"  [ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mv_status_api():
    """测试物化视图状态API"""
    base_url = "http://localhost:8001/api"
    
    print("\n[2] 测试物化视图状态API...")
    try:
        # ⭐ 修复：禁用代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.get(
            f"{base_url}/mv/status",
            timeout=30,
            proxies=proxies  # 禁用代理
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("  [OK] API端点存在")
            data = response.json()
            views = data.get('data', {}).get('views', [])
            print(f"  找到 {len(views)} 个物化视图")
            return True
        else:
            print(f"  [WARNING] 意外的状态码: {response.status_code}")
            print(f"  响应: {response.text}")
            return False
            
    except Exception as e:
        print(f"  [ERROR] 测试失败: {e}")
        return False

if __name__ == "__main__":
    print("\n开始测试...")
    
    # 测试状态API（更快）
    status_ok = test_mv_status_api()
    
    # 测试刷新API
    refresh_ok = test_mv_refresh_api()
    
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    print(f"状态API: {'[OK]' if status_ok else '[FAIL]'}")
    print(f"刷新API: {'[OK]' if refresh_ok else '[FAIL]'}")
    
    if not refresh_ok:
        print("\n⚠️  如果刷新API返回404，请重启后端服务:")
        print("   1. 停止当前后端服务（Ctrl+C）")
        print("   2. 重新启动: python run.py")
        print("   3. 等待服务启动完成后再测试")

