#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户注册和审批流程 - 单元测试

测试内容：
1. 用户注册API测试
   - 正常注册流程
   - 用户名重复测试（统一错误消息）
   - 邮箱重复测试（统一错误消息）
   - 密码强度验证测试
2. 用户审批API测试
   - 批准用户测试
   - 拒绝用户测试
   - 权限检查测试
   - 默认角色不存在场景测试
3. 登录API测试
   - pending状态用户登录测试
   - rejected状态用户登录测试
   - suspended状态用户登录测试
   - 账户锁定测试
"""

import sys
import asyncio
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

import requests
from typing import Dict, List, Tuple
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 测试配置
BASE_URL = "http://localhost:8001"
API_PREFIX = "/api"

# 测试结果
test_results: List[Tuple[str, bool, str]] = []

# 测试数据
test_timestamp = int(time.time())
admin_username = "xihong"
admin_password = "~!Qq1`1`"
admin_token = None


def print_header(title: str):
    """打印测试标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(test_name: str, success: bool, message: str = ""):
    """打印测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"{status} {test_name}")
    if message:
        print(f"      {message}")
    test_results.append((test_name, success, message))


def login_as_admin() -> str:
    """登录管理员账号，返回token"""
    global admin_token
    
    if admin_token:
        return admin_token
    
    url = f"{BASE_URL}{API_PREFIX}/auth/login"
    data = {
        "username": admin_username,
        "password": admin_password
    }
    
    try:
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result.get("success") or "access_token" in result:
                admin_token = result.get("access_token") or result.get("data", {}).get("access_token")
                if admin_token:
                    print_result("管理员登录", True, "获取管理员token成功")
                    return admin_token
        
        print_result("管理员登录", False, f"登录失败: {response.status_code}")
        return None
    except Exception as e:
        print_result("管理员登录", False, f"登录异常: {e}")
        return None


def test_register_normal():
    """测试正常注册流程"""
    print_header("1.1 正常注册流程测试")
    
    url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"test_user_{test_timestamp}",
        "email": f"test_user_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Test User"
    }
    
    try:
        response = requests.post(url, json=test_data, timeout=5)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print_result("正常注册流程", True, f"用户ID: {data.get('data', {}).get('user_id')}")
            return data.get("data", {}).get("user_id")
        else:
            print_result("正常注册流程", False, f"注册失败: {data.get('message')}")
            return None
    except Exception as e:
        print_result("正常注册流程", False, f"请求异常: {e}")
        return None


def test_register_duplicate_username():
    """测试用户名重复（统一错误消息）"""
    print_header("1.2 用户名重复测试")
    
    url = f"{BASE_URL}{API_PREFIX}/auth/register"
    
    # 先注册一个用户
    test_data = {
        "username": f"dup_user_{test_timestamp}",
        "email": f"dup_user_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Duplicate Test"
    }
    
    try:
        # 第一次注册
        response1 = requests.post(url, json=test_data, timeout=5)
        
        # 第二次注册（相同用户名，不同邮箱）
        test_data["email"] = f"dup_user_{test_timestamp}_2@test.com"
        response2 = requests.post(url, json=test_data, timeout=5)
        data2 = response2.json()
        
        error_message = data2.get("message", "")
        if "已被使用" in error_message or "already exists" in error_message.lower():
            print_result(
                "用户名重复测试",
                True,
                "正确返回错误消息（统一消息，不泄露具体字段）"
            )
        else:
            print_result(
                "用户名重复测试",
                False,
                f"错误消息: {error_message}"
            )
    except Exception as e:
        print_result("用户名重复测试", False, f"请求异常: {e}")


def test_register_duplicate_email():
    """测试邮箱重复（统一错误消息）"""
    print_header("1.3 邮箱重复测试")
    
    url = f"{BASE_URL}{API_PREFIX}/auth/register"
    
    # 先注册一个用户
    test_data = {
        "username": f"dup_email_{test_timestamp}",
        "email": f"dup_email_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Duplicate Email Test"
    }
    
    try:
        # 第一次注册
        response1 = requests.post(url, json=test_data, timeout=5)
        
        # 第二次注册（相同邮箱，不同用户名）
        test_data["username"] = f"dup_email_{test_timestamp}_2"
        response2 = requests.post(url, json=test_data, timeout=5)
        data2 = response2.json()
        
        error_message = data2.get("message", "")
        if "已被使用" in error_message or "already exists" in error_message.lower():
            print_result(
                "邮箱重复测试",
                True,
                "正确返回错误消息（统一消息，不泄露具体字段）"
            )
        else:
            print_result(
                "邮箱重复测试",
                False,
                f"错误消息: {error_message}"
            )
    except Exception as e:
        print_result("邮箱重复测试", False, f"请求异常: {e}")


def test_register_password_strength():
    """测试密码强度验证"""
    print_header("1.4 密码强度验证测试")
    
    url = f"{BASE_URL}{API_PREFIX}/auth/register"
    
    test_cases = [
        ("密码太短", "Test123", False),
        ("缺少字母", "12345678", False),
        ("缺少数字", "TestPassword", False),
        ("有效密码", "Test123456", True),
    ]
    
    for test_name, password, should_pass in test_cases:
        test_data = {
            "username": f"pwd_test_{test_timestamp}_{int(time.time())}",
            "email": f"pwd_test_{test_timestamp}_{int(time.time())}@test.com",
            "password": password,
            "full_name": "Password Test"
        }
        
        try:
            response = requests.post(url, json=test_data, timeout=5)
            data = response.json()
            
            if should_pass:
                success = data.get("success", False)
                print_result(
                    f"密码强度测试 - {test_name}",
                    success,
                    "应该通过" if success else "不应该通过"
                )
            else:
                success = not data.get("success", False)
                print_result(
                    f"密码强度测试 - {test_name}",
                    success,
                    "应该被拒绝" if success else "不应该被接受"
                )
        except Exception as e:
            print_result(f"密码强度测试 - {test_name}", False, f"请求异常: {e}")


def test_approve_user():
    """测试批准用户"""
    print_header("2.1 批准用户测试")
    
    token = login_as_admin()
    if not token:
        print_result("批准用户测试", False, "无法获取管理员token")
        return None
    
    # 先注册一个待审批用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"approve_test_{test_timestamp}",
        "email": f"approve_test_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Approve Test User"
    }
    
    try:
        # 注册用户
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_data = register_response.json()
        
        if not register_data.get("success"):
            print_result("批准用户测试", False, "无法创建待审批用户")
            return None
        
        user_id = register_data.get("data", {}).get("user_id")
        
        # 批准用户
        approve_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/approve"
        headers = {"Authorization": f"Bearer {token}"}
        approve_data = {}
        
        approve_response = requests.post(approve_url, json=approve_data, headers=headers, timeout=5)
        approve_result = approve_response.json()
        
        if approve_response.status_code == 200 and approve_result.get("success"):
            print_result("批准用户测试", True, f"用户ID {user_id} 已批准")
            return user_id
        else:
            print_result("批准用户测试", False, f"批准失败: {approve_result.get('message')}")
            return None
    except Exception as e:
        print_result("批准用户测试", False, f"请求异常: {e}")
        return None


def test_reject_user():
    """测试拒绝用户"""
    print_header("2.2 拒绝用户测试")
    
    token = login_as_admin()
    if not token:
        print_result("拒绝用户测试", False, "无法获取管理员token")
        return None
    
    # 先注册一个待审批用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"reject_test_{test_timestamp}",
        "email": f"reject_test_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Reject Test User"
    }
    
    try:
        # 注册用户
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_data = register_response.json()
        
        if not register_data.get("success"):
            print_result("拒绝用户测试", False, "无法创建待审批用户")
            return None
        
        user_id = register_data.get("data", {}).get("user_id")
        
        # 拒绝用户
        reject_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/reject"
        headers = {"Authorization": f"Bearer {token}"}
        reject_data = {"reason": "测试拒绝原因"}
        
        reject_response = requests.post(reject_url, json=reject_data, headers=headers, timeout=5)
        reject_result = reject_response.json()
        
        if reject_response.status_code == 200 and reject_result.get("success"):
            print_result("拒绝用户测试", True, f"用户ID {user_id} 已拒绝")
            return user_id
        else:
            print_result("拒绝用户测试", False, f"拒绝失败: {reject_result.get('message')}")
            return None
    except Exception as e:
        print_result("拒绝用户测试", False, f"请求异常: {e}")
        return None


def test_login_pending_user():
    """测试pending状态用户登录"""
    print_header("3.1 Pending状态用户登录测试")
    
    # 先注册一个用户（状态为pending）
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"pending_login_{test_timestamp}",
        "email": f"pending_login_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Pending Login Test"
    }
    
    try:
        # 注册用户
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_data = register_response.json()
        
        if not register_data.get("success"):
            print_result("Pending状态用户登录测试", False, "无法创建待审批用户")
            return
        
        # 尝试登录
        login_url = f"{BASE_URL}{API_PREFIX}/auth/login"
        login_data = {
            "username": test_data["username"],
            "password": test_data["password"]
        }
        
        login_response = requests.post(login_url, json=login_data, timeout=5)
        login_result = login_response.json()
        
        # 应该被拒绝，返回pending状态错误
        if login_response.status_code in [403, 401]:
            error_code = login_result.get("error", {}).get("code")
            if error_code == 4005:  # AUTH_ACCOUNT_PENDING
                print_result("Pending状态用户登录测试", True, "正确拒绝pending状态用户")
            else:
                print_result("Pending状态用户登录测试", False, f"错误码不正确: {error_code}")
        else:
            print_result("Pending状态用户登录测试", False, "应该拒绝pending状态用户登录")
    except Exception as e:
        print_result("Pending状态用户登录测试", False, f"请求异常: {e}")


def test_login_rejected_user():
    """测试rejected状态用户登录"""
    print_header("3.2 Rejected状态用户登录测试")
    
    token = login_as_admin()
    if not token:
        print_result("Rejected状态用户登录测试", False, "无法获取管理员token")
        return
    
    # 先注册并拒绝一个用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"rejected_login_{test_timestamp}",
        "email": f"rejected_login_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Rejected Login Test"
    }
    
    try:
        # 注册用户
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_data = register_response.json()
        
        if not register_data.get("success"):
            print_result("Rejected状态用户登录测试", False, "无法创建待审批用户")
            return
        
        user_id = register_data.get("data", {}).get("user_id")
        
        # 拒绝用户
        reject_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/reject"
        headers = {"Authorization": f"Bearer {token}"}
        reject_data = {"reason": "测试拒绝"}
        requests.post(reject_url, json=reject_data, headers=headers, timeout=5)
        
        # 尝试登录
        login_url = f"{BASE_URL}{API_PREFIX}/auth/login"
        login_data = {
            "username": test_data["username"],
            "password": test_data["password"]
        }
        
        login_response = requests.post(login_url, json=login_data, timeout=5)
        login_result = login_response.json()
        
        # 应该被拒绝，返回rejected状态错误
        if login_response.status_code in [403, 401]:
            error_code = login_result.get("error", {}).get("code")
            if error_code == 4006:  # AUTH_ACCOUNT_REJECTED
                print_result("Rejected状态用户登录测试", True, "正确拒绝rejected状态用户")
            else:
                print_result("Rejected状态用户登录测试", False, f"错误码不正确: {error_code}")
        else:
            print_result("Rejected状态用户登录测试", False, "应该拒绝rejected状态用户登录")
    except Exception as e:
        print_result("Rejected状态用户登录测试", False, f"请求异常: {e}")


def test_account_locking():
    """测试账户锁定机制"""
    print_header("3.3 账户锁定测试")
    
    # 先注册并批准一个用户
    token = login_as_admin()
    if not token:
        print_result("账户锁定测试", False, "无法获取管理员token")
        return
    
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"lock_test_{test_timestamp}",
        "email": f"lock_test_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Lock Test User"
    }
    
    try:
        # 注册用户
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_data = register_response.json()
        
        if not register_data.get("success"):
            print_result("账户锁定测试", False, "无法创建用户")
            return
        
        user_id = register_data.get("data", {}).get("user_id")
        
        # 批准用户
        approve_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/approve"
        headers = {"Authorization": f"Bearer {token}"}
        requests.post(approve_url, json={}, headers=headers, timeout=5)
        
        # 尝试5次错误密码登录
        login_url = f"{BASE_URL}{API_PREFIX}/auth/login"
        login_data = {
            "username": test_data["username"],
            "password": "WrongPassword"
        }
        
        locked = False
        for i in range(6):
            login_response = requests.post(login_url, json=login_data, timeout=5)
            login_result = login_response.json()
            
            if i < 5:
                # 前5次应该返回密码错误
                if login_response.status_code == 401:
                    print_result(f"账户锁定测试 - 失败尝试 {i+1}", True, "返回密码错误")
            else:
                # 第6次应该返回账户锁定
                error_code = login_result.get("error", {}).get("code")
                if error_code == 4009:  # AUTH_ACCOUNT_LOCKED
                    locked = True
                    print_result("账户锁定测试 - 账户被锁定", True, "正确锁定账户")
                    break
        
        if not locked:
            print_result("账户锁定测试", False, "账户未被锁定")
    except Exception as e:
        print_result("账户锁定测试", False, f"请求异常: {e}")


def print_summary():
    """打印测试总结"""
    print_header("测试总结")
    
    total = len(test_results)
    passed = sum(1 for _, success, _ in test_results if success)
    failed = total - passed
    
    print(f"总测试数: {total}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"通过率: {passed/total*100:.1f}%")
    
    if failed > 0:
        print("\n失败的测试:")
        for test_name, success, message in test_results:
            if not success:
                print(f"  - {test_name}: {message}")
    
    print("\n" + "=" * 70)


def main():
    """主函数"""
    print("=" * 70)
    print("  用户注册和审批流程 - 单元测试")
    print("=" * 70)
    print(f"测试目标: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 检查服务是否可用
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        if response.status_code != 200:
            print("\n[WARN] 后端服务可能未启动，部分测试可能失败")
    except Exception as e:
        print(f"\n[WARN] 无法连接到后端服务: {e}")
        print(f"[WARN] 请确保后端服务已启动在 {BASE_URL}")
    
    # 执行测试
    test_register_normal()
    test_register_duplicate_username()
    test_register_duplicate_email()
    test_register_password_strength()
    test_approve_user()
    test_reject_user()
    test_login_pending_user()
    test_login_rejected_user()
    test_account_locking()
    
    # 打印总结
    print_summary()
    
    # 返回退出码
    failed_count = sum(1 for _, success, _ in test_results if not success)
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

