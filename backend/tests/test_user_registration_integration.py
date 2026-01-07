#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户注册和审批流程 - 集成测试

测试内容：
1. 完整的注册-审批-登录流程测试
2. 管理员审批工作流测试
3. 密码重置和账户解锁流程测试
4. 会话管理流程测试
"""

import sys
import asyncio
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

import requests
from typing import Dict, List, Tuple, Optional
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


def login_as_admin() -> Optional[str]:
    """登录管理员账号，返回token"""
    url = f"{BASE_URL}{API_PREFIX}/auth/login"
    data = {
        "username": admin_username,
        "password": admin_password
    }
    
    try:
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            result = response.json()
            token = result.get("access_token") or result.get("data", {}).get("access_token")
            if token:
                return token
        return None
    except Exception as e:
        logger.error(f"管理员登录失败: {e}")
        return None


def test_complete_registration_approval_login_flow():
    """测试完整的注册-审批-登录流程"""
    print_header("1. 完整的注册-审批-登录流程测试")
    
    # 步骤1: 注册新用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"flow_test_{test_timestamp}",
        "email": f"flow_test_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Flow Test User"
    }
    
    try:
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_result = register_response.json()
        
        if not register_result.get("success"):
            print_result("注册步骤", False, f"注册失败: {register_result.get('message')}")
            return False
        
        user_id = register_result.get("data", {}).get("user_id")
        print_result("注册步骤", True, f"用户ID: {user_id}, 状态: pending")
        
        # 步骤2: 尝试登录（应该被拒绝）
        login_url = f"{BASE_URL}{API_PREFIX}/auth/login"
        login_data = {
            "username": test_data["username"],
            "password": test_data["password"]
        }
        
        login_response = requests.post(login_url, json=login_data, timeout=5)
        login_result = login_response.json()
        
        if login_response.status_code == 403:
            error_code = login_result.get("error", {}).get("code")
            if error_code == 4005:  # AUTH_ACCOUNT_PENDING
                print_result("登录步骤（pending状态）", True, "正确拒绝pending状态用户")
            else:
                print_result("登录步骤（pending状态）", False, f"错误码不正确: {error_code}")
        else:
            print_result("登录步骤（pending状态）", False, "应该拒绝pending状态用户")
        
        # 步骤3: 管理员批准用户
        token = login_as_admin()
        if not token:
            print_result("审批步骤", False, "无法获取管理员token")
            return False
        
        approve_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/approve"
        headers = {"Authorization": f"Bearer {token}"}
        approve_response = requests.post(approve_url, json={}, headers=headers, timeout=5)
        approve_result = approve_response.json()
        
        if approve_response.status_code == 200 and approve_result.get("success"):
            print_result("审批步骤", True, f"用户ID {user_id} 已批准")
        else:
            print_result("审批步骤", False, f"批准失败: {approve_result.get('message')}")
            return False
        
        # 步骤4: 再次尝试登录（应该成功）
        login_response2 = requests.post(login_url, json=login_data, timeout=5)
        login_result2 = login_response2.json()
        
        if login_response2.status_code == 200:
            token = login_result2.get("access_token") or login_result2.get("data", {}).get("access_token")
            if token:
                print_result("登录步骤（active状态）", True, "登录成功，获取到token")
                return True
            else:
                print_result("登录步骤（active状态）", False, "登录成功但未返回token")
                return False
        else:
            print_result("登录步骤（active状态）", False, f"登录失败: {login_result2.get('message')}")
            return False
        
    except Exception as e:
        print_result("完整流程测试", False, f"请求异常: {e}")
        return False


def test_admin_approval_workflow():
    """测试管理员审批工作流"""
    print_header("2. 管理员审批工作流测试")
    
    token = login_as_admin()
    if not token:
        print_result("管理员审批工作流", False, "无法获取管理员token")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 步骤1: 注册多个待审批用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    user_ids = []
    
    for i in range(3):
        test_data = {
            "username": f"approval_workflow_{test_timestamp}_{i}",
            "email": f"approval_workflow_{test_timestamp}_{i}@test.com",
            "password": "Test123456",
            "full_name": f"Approval Workflow User {i}"
        }
        
        try:
            register_response = requests.post(register_url, json=test_data, timeout=5)
            register_result = register_response.json()
            
            if register_result.get("success"):
                user_id = register_result.get("data", {}).get("user_id")
                user_ids.append(user_id)
        except Exception as e:
            logger.error(f"注册用户失败: {e}")
    
    if len(user_ids) == 0:
        print_result("管理员审批工作流", False, "无法创建待审批用户")
        return False
    
    print_result("创建待审批用户", True, f"创建了 {len(user_ids)} 个待审批用户")
    
    # 步骤2: 获取待审批用户列表
    pending_url = f"{BASE_URL}{API_PREFIX}/users/pending"
    pending_response = requests.get(pending_url, headers=headers, timeout=5)
    pending_result = pending_response.json()
    
    if pending_response.status_code == 200 and pending_result.get("success"):
        pending_users = pending_result.get("data", [])
        print_result("获取待审批用户列表", True, f"找到 {len(pending_users)} 个待审批用户")
    else:
        print_result("获取待审批用户列表", False, "获取失败")
        return False
    
    # 步骤3: 批准第一个用户
    if len(user_ids) > 0:
        approve_url = f"{BASE_URL}{API_PREFIX}/users/{user_ids[0]}/approve"
        approve_response = requests.post(approve_url, json={}, headers=headers, timeout=5)
        approve_result = approve_response.json()
        
        if approve_response.status_code == 200 and approve_result.get("success"):
            print_result("批准用户", True, f"用户ID {user_ids[0]} 已批准")
        else:
            print_result("批准用户", False, "批准失败")
    
    # 步骤4: 拒绝第二个用户
    if len(user_ids) > 1:
        reject_url = f"{BASE_URL}{API_PREFIX}/users/{user_ids[1]}/reject"
        reject_data = {"reason": "测试拒绝原因"}
        reject_response = requests.post(reject_url, json=reject_data, headers=headers, timeout=5)
        reject_result = reject_response.json()
        
        if reject_response.status_code == 200 and reject_result.get("success"):
            print_result("拒绝用户", True, f"用户ID {user_ids[1]} 已拒绝")
        else:
            print_result("拒绝用户", False, "拒绝失败")
    
    return True


def test_password_reset_and_unlock_flow():
    """测试密码重置和账户解锁流程"""
    print_header("3. 密码重置和账户解锁流程测试")
    
    token = login_as_admin()
    if not token:
        print_result("密码重置和账户解锁流程", False, "无法获取管理员token")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 步骤1: 注册并批准一个用户
    register_url = f"{BASE_URL}{API_PREFIX}/auth/register"
    test_data = {
        "username": f"reset_test_{test_timestamp}",
        "email": f"reset_test_{test_timestamp}@test.com",
        "password": "Test123456",
        "full_name": "Reset Test User"
    }
    
    try:
        register_response = requests.post(register_url, json=test_data, timeout=5)
        register_result = register_response.json()
        
        if not register_result.get("success"):
            print_result("密码重置流程", False, "无法创建用户")
            return False
        
        user_id = register_result.get("data", {}).get("user_id")
        
        # 批准用户
        approve_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/approve"
        requests.post(approve_url, json={}, headers=headers, timeout=5)
        
        # 步骤2: 重置密码（生成临时密码）
        reset_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/reset-password"
        reset_data = {"generate_temp_password": True}
        reset_response = requests.post(reset_url, json=reset_data, headers=headers, timeout=5)
        reset_result = reset_response.json()
        
        if reset_response.status_code == 200 and reset_result.get("success"):
            temp_password = reset_result.get("data", {}).get("temp_password")
            if temp_password:
                print_result("密码重置（临时密码）", True, f"临时密码已生成: {temp_password[:4]}****")
            else:
                print_result("密码重置（临时密码）", False, "未返回临时密码")
        else:
            print_result("密码重置（临时密码）", False, "重置失败")
        
        # 步骤3: 使用临时密码登录
        if temp_password:
            login_url = f"{BASE_URL}{API_PREFIX}/auth/login"
            login_data = {
                "username": test_data["username"],
                "password": temp_password
            }
            
            login_response = requests.post(login_url, json=login_data, timeout=5)
            if login_response.status_code == 200:
                print_result("使用临时密码登录", True, "登录成功")
            else:
                print_result("使用临时密码登录", False, "登录失败")
        
        # 步骤4: 测试账户锁定和解锁
        # 先锁定账户（通过5次错误登录）
        login_data_wrong = {
            "username": test_data["username"],
            "password": "WrongPassword"
        }
        
        for i in range(5):
            requests.post(login_url, json=login_data_wrong, timeout=5)
        
        # 第6次应该被锁定
        lock_response = requests.post(login_url, json=login_data_wrong, timeout=5)
        lock_result = lock_response.json()
        
        if lock_response.status_code == 403:
            error_code = lock_result.get("error", {}).get("code")
            if error_code == 4009:  # AUTH_ACCOUNT_LOCKED
                print_result("账户锁定", True, "账户已被锁定")
                
                # 解锁账户
                unlock_url = f"{BASE_URL}{API_PREFIX}/users/{user_id}/unlock"
                unlock_data = {"reason": "测试解锁"}
                unlock_response = requests.post(unlock_url, json=unlock_data, headers=headers, timeout=5)
                unlock_result = unlock_response.json()
                
                if unlock_response.status_code == 200 and unlock_result.get("success"):
                    print_result("账户解锁", True, "账户已解锁")
                else:
                    print_result("账户解锁", False, "解锁失败")
            else:
                print_result("账户锁定", False, f"错误码不正确: {error_code}")
        else:
            print_result("账户锁定", False, "账户未被锁定")
        
        return True
        
    except Exception as e:
        print_result("密码重置和账户解锁流程", False, f"请求异常: {e}")
        return False


def test_session_management_flow():
    """测试会话管理流程"""
    print_header("4. 会话管理流程测试")
    
    token = login_as_admin()
    if not token:
        print_result("会话管理流程", False, "无法获取管理员token")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # 步骤1: 获取当前用户的活跃会话列表
        sessions_url = f"{BASE_URL}{API_PREFIX}/users/me/sessions"
        sessions_response = requests.get(sessions_url, headers=headers, timeout=5)
        sessions_result = sessions_response.json()
        
        if sessions_response.status_code == 200 and sessions_result.get("success"):
            sessions = sessions_result.get("data", [])
            print_result("获取会话列表", True, f"找到 {len(sessions)} 个活跃会话")
            
            # 步骤2: 如果有其他会话，撤销一个
            if len(sessions) > 1:
                # 找到非当前会话
                other_session = None
                for session in sessions:
                    if not session.get("is_current"):
                        other_session = session
                        break
                
                if other_session:
                    session_id = other_session.get("session_id")
                    revoke_url = f"{BASE_URL}{API_PREFIX}/users/me/sessions/{session_id}"
                    revoke_response = requests.delete(revoke_url, headers=headers, timeout=5)
                    revoke_result = revoke_response.json()
                    
                    if revoke_response.status_code == 200 and revoke_result.get("success"):
                        print_result("撤销指定会话", True, f"会话 {session_id[:8]}... 已撤销")
                    else:
                        print_result("撤销指定会话", False, "撤销失败")
            
            # 步骤3: 撤销所有其他会话
            revoke_all_url = f"{BASE_URL}{API_PREFIX}/users/me/sessions"
            revoke_all_response = requests.delete(revoke_all_url, headers=headers, timeout=5)
            revoke_all_result = revoke_all_response.json()
            
            if revoke_all_response.status_code == 200 and revoke_all_result.get("success"):
                revoked_count = revoke_all_result.get("data", {}).get("revoked_count", 0)
                print_result("撤销所有其他会话", True, f"已撤销 {revoked_count} 个会话")
            else:
                print_result("撤销所有其他会话", False, "撤销失败")
        else:
            print_result("获取会话列表", False, "获取失败")
            return False
        
        return True
        
    except Exception as e:
        print_result("会话管理流程", False, f"请求异常: {e}")
        return False


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
    print("  用户注册和审批流程 - 集成测试")
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
    test_complete_registration_approval_login_flow()
    test_admin_approval_workflow()
    test_password_reset_and_unlock_flow()
    test_session_management_flow()
    
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

