#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的用户注册和审批API测试脚本

快速测试API基本功能
"""

import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_register():
    """测试用户注册"""
    print("[TEST 1] 用户注册")
    url = f"{BASE_URL}/auth/register"
    data = {
        "username": "test_user_simple_001",
        "email": "test_simple_001@test.com",
        "password": "test123456",
        "full_name": "简单测试用户001"
    }
    
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"  状态码: {response.status_code}")
        result = response.json()
        print(f"  响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200 and result.get("success"):
            user_id = result["data"]["user_id"]
            print(f"  [SUCCESS] 用户注册成功，ID: {user_id}")
            return user_id
        else:
            print(f"  [FAIL] 注册失败")
            return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def test_login_pending():
    """测试pending用户登录（应该失败）"""
    print("\n[TEST 2] Pending用户登录（预期失败）")
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": "test_user_simple_001",
        "password": "test123456"
    }
    
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"  状态码: {response.status_code}")
        result = response.json()
        print(f"  响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 403 and result.get("code") == 4005:
            print(f"  [SUCCESS] Pending用户无法登录（符合预期）")
            return True
        else:
            print(f"  [WARN] 状态不符合预期")
            return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def main():
    print("="*60)
    print("用户注册和审批API简化测试")
    print("="*60)
    print("\n确保后端服务正在运行 (http://localhost:8000)\n")
    
    # 测试注册
    user_id = test_register()
    
    if user_id:
        # 测试pending用户登录
        test_login_pending()
        
        print("\n" + "="*60)
        print("测试完成")
        print("="*60)
        print("\n如需测试审批功能，请：")
        print("1. 使用管理员账号登录获取token")
        print("2. 调用 POST /api/users/{user_id}/approve")
        print(f"3. 用户ID: {user_id}")
    else:
        print("\n[ERROR] 用户注册失败，无法继续测试")

if __name__ == "__main__":
    main()

