#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户注册和审批API手动测试脚本

使用方法：
    python backend/test_registration_api_manual.py

测试步骤：
1. 启动后端服务（确保数据库已运行）
2. 运行此脚本
3. 查看输出结果
"""

import sys
import requests
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# API基础URL
BASE_URL = "http://localhost:8000/api"

def print_response(title: str, response: requests.Response):
    """打印响应结果"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except:
        print(f"Response Text: {response.text}")
    print(f"{'='*60}\n")


def test_user_registration():
    """测试用户注册"""
    print("[TEST] 测试用户注册API")
    
    url = f"{BASE_URL}/auth/register"
    data = {
        "username": "test_user_001",
        "email": "test_user_001@test.com",
        "password": "test123456",
        "full_name": "测试用户001",
        "phone": "13800138001",
        "department": "测试部门"
    }
    
    response = requests.post(url, json=data)
    print_response("用户注册响应", response)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            user_id = result["data"]["user_id"]
            print(f"[SUCCESS] 用户注册成功，用户ID: {user_id}")
            return user_id
        else:
            print(f"[FAIL] 用户注册失败: {result.get('message')}")
    else:
        print(f"[FAIL] 用户注册失败，状态码: {response.status_code}")
    
    return None


def test_user_login_pending(user_id: int):
    """测试pending状态用户无法登录"""
    print("[TEST] 测试pending状态用户登录（应该失败）")
    
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": "test_user_001",
        "password": "test123456"
    }
    
    response = requests.post(url, json=data)
    print_response("Pending用户登录响应（预期403）", response)
    
    if response.status_code == 403:
        result = response.json()
        if result.get("code") == 4005:  # AUTH_ACCOUNT_PENDING
            print("[SUCCESS] Pending用户无法登录（符合预期）")
            return True
    
    print("[FAIL] Pending用户登录测试失败")
    return False


def test_get_pending_users(admin_token: str):
    """测试获取待审批用户列表"""
    print("[TEST] 测试获取待审批用户列表")
    
    url = f"{BASE_URL}/users/pending"
    headers = {"Authorization": f"Bearer {admin_token}"}
    params = {"page": 1, "page_size": 20}
    
    response = requests.get(url, headers=headers, params=params)
    print_response("待审批用户列表响应", response)
    
    if response.status_code == 200:
        users = response.json()
        print(f"[SUCCESS] 获取待审批用户列表成功，共 {len(users)} 个用户")
        return True
    
    print(f"[FAIL] 获取待审批用户列表失败，状态码: {response.status_code}")
    return False


def test_user_approval(user_id: int, admin_token: str):
    """测试用户审批"""
    print("[TEST] 测试用户审批API")
    
    url = f"{BASE_URL}/users/{user_id}/approve"
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = {
        "notes": "测试审批通过"
    }
    
    response = requests.post(url, json=data, headers=headers)
    print_response("用户审批响应", response)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success") and result["data"]["status"] == "active":
            print("[SUCCESS] 用户审批成功")
            return True
    
    print(f"[FAIL] 用户审批失败，状态码: {response.status_code}")
    return False


def test_user_login_after_approval():
    """测试审批后用户登录"""
    print("[TEST] 测试审批后用户登录（应该成功）")
    
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": "test_user_001",
        "password": "test123456"
    }
    
    response = requests.post(url, json=data)
    print_response("审批后用户登录响应（预期200）", response)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            print("[SUCCESS] 审批后用户登录成功")
            return result["data"]["access_token"]
    
    print("[FAIL] 审批后用户登录失败")
    return None


def get_admin_token():
    """获取管理员token（需要先有一个admin用户）"""
    print("[TEST] 获取管理员Token")
    
    url = f"{BASE_URL}/auth/login"
    # 注意：这里需要先有一个admin用户，如果没有，需要手动创建
    # 或者使用现有的管理员账号
    data = {
        "username": "admin",  # 修改为实际的管理员用户名
        "password": "admin123"  # 修改为实际的管理员密码
    }
    
    response = requests.post(url, json=data)
    print_response("管理员登录响应", response)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            token = result["data"]["access_token"]
            print(f"[SUCCESS] 获取管理员Token成功")
            return token
    
    print("[WARN] 无法获取管理员Token，可能需要先创建admin用户")
    print("[WARN] 或者修改脚本中的admin用户名和密码")
    return None


def main():
    """主测试函数"""
    print("="*60)
    print("用户注册和审批API手动测试")
    print("="*60)
    print("\n注意事项：")
    print("1. 确保后端服务正在运行（http://localhost:8000）")
    print("2. 确保数据库已连接")
    print("3. 如果测试失败，检查是否有admin用户")
    print("="*60)
    
    try:
        # 测试1: 用户注册
        user_id = test_user_registration()
        if not user_id:
            print("\n[ERROR] 用户注册失败，停止测试")
            return
        
        # 测试2: pending状态用户无法登录
        test_user_login_pending(user_id)
        
        # 测试3: 获取管理员token
        admin_token = get_admin_token()
        if not admin_token:
            print("\n[ERROR] 无法获取管理员Token，跳过审批相关测试")
            print("[INFO] 需要先创建一个admin用户才能测试审批功能")
            return
        
        # 测试4: 获取待审批用户列表
        test_get_pending_users(admin_token)
        
        # 测试5: 用户审批
        if test_user_approval(user_id, admin_token):
            # 测试6: 审批后用户登录
            user_token = test_user_login_after_approval()
            if user_token:
                print("\n[SUCCESS] 所有测试通过！")
            else:
                print("\n[PARTIAL] 部分测试通过，但审批后登录失败")
        else:
            print("\n[PARTIAL] 部分测试通过，但审批失败")
    
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] 无法连接到后端服务")
        print("请确保后端服务正在运行: python run.py 或 python run_new.py")
    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

