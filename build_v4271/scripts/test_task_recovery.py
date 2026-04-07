#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务恢复机制测试脚本

验证 Celery Worker 重启后，未完成的任务能够自动恢复。
"""

import sys
import time
import requests
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# API 配置
API_BASE_URL = "http://localhost:8001"
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin"
AUTH_TOKEN = None


def print_header(title):
    """打印测试标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(test_name, success, message=""):
    """打印测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    color_code = "\033[92m" if success else "\033[91m"
    reset_code = "\033[0m"
    print(f"{color_code}{status}{reset_code} {test_name}")
    if message:
        print(f"      {message}")


def login():
    """登录获取认证 token"""
    global AUTH_TOKEN
    print_header("登录获取认证 Token")
    
    payload = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "remember_me": True
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            AUTH_TOKEN = data.get("access_token")
            if AUTH_TOKEN:
                print_result("登录获取 Token", True, "成功获取 Access Token")
                return True
            else:
                print_result("登录获取 Token", False, "未在响应中找到 Access Token")
                return False
        else:
            print_result("登录获取 Token", False, f"状态码: {response.status_code}")
            return False
    except Exception as e:
        print_result("登录获取 Token", False, f"请求失败: {str(e)}")
        return False


def find_available_file_id():
    """查找可用的文件ID"""
    print_header("查找可用的文件ID")
    
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        # 查询文件列表（获取第一个文件）
        response = requests.get(
            f"{API_BASE_URL}/api/data-sync/files",
            params={"page": 1, "page_size": 1, "status": "pending"},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                files = data.get("data", {}).get("files", [])
                if files:
                    file_id = files[0].get("id")
                    print_result("查找文件ID", True, f"找到文件ID: {file_id}")
                    return file_id
                else:
                    print_result("查找文件ID", False, "没有找到待同步的文件")
                    return None
            else:
                print_result("查找文件ID", False, f"响应: {data.get('message', '未知错误')}")
                return None
        else:
            print_result("查找文件ID", False, f"状态码: {response.status_code}")
            return None
    except Exception as e:
        print_result("查找文件ID", False, f"请求失败: {str(e)}")
        return None


def submit_task(file_id):
    """提交任务"""
    print_header("提交测试任务")
    
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    payload = {
        "file_id": file_id,
        "priority": 5
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/data-sync/single",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                task_id = data.get("data", {}).get("task_id")
                celery_task_id = data.get("data", {}).get("celery_task_id")
                print_result("任务提交", True, f"task_id: {task_id}")
                if celery_task_id:
                    print(f"      celery_task_id: {celery_task_id}")
                    return celery_task_id
                else:
                    print("      [WARN] 未返回 celery_task_id，可能使用了降级模式")
                    return None
            else:
                print_result("任务提交", False, f"响应: {data.get('message', '未知错误')}")
                return None
        else:
            print_result("任务提交", False, f"状态码: {response.status_code}, 响应: {response.text}")
            return None
    except Exception as e:
        print_result("任务提交", False, f"请求失败: {str(e)}")
        return None


def query_task_status(celery_task_id):
    """查询任务状态"""
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/data-sync/task-status/{celery_task_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            # 直接返回响应数据（任务状态端点直接返回 CeleryTaskStatusResponse）
            state = data.get("state", "UNKNOWN")
            ready = data.get("ready", False)
            successful = data.get("successful")
            
            return {
                "state": state,
                "ready": ready,
                "successful": successful,
                "data": data
            }
        else:
            return None
    except Exception as e:
        return None


def test_task_recovery():
    """测试任务恢复机制"""
    print_header("任务恢复机制测试")
    
    print("\n[步骤 1] 提交任务")
    file_id = find_available_file_id()
    if not file_id:
        print("\n[ERROR] 无法找到可用的文件ID，测试终止")
        print("        [提示] 请确保数据库中有待同步的文件（status='pending'）")
        return False
    
    celery_task_id = submit_task(file_id)
    if not celery_task_id:
        print("\n[ERROR] 无法提交任务，测试终止")
        return False
    
    print("\n[步骤 2] 查询任务初始状态")
    status = query_task_status(celery_task_id)
    if not status:
        print("\n[ERROR] 无法查询任务状态")
        return False
    
    initial_state = status["state"]
    print(f"      初始状态: {initial_state}")
    print(f"      是否完成: {status['ready']}")
    
    print("\n[步骤 3] 等待任务开始执行（5秒）...")
    time.sleep(5)
    
    status = query_task_status(celery_task_id)
    if status:
        current_state = status["state"]
        print(f"      当前状态: {current_state}")
        print(f"      是否完成: {status['ready']}")
    
    print("\n" + "=" * 70)
    print("  [WARN] 重要提示")
    print("=" * 70)
    print("\n现在请执行以下操作：")
    print("1. 停止 Celery Worker（Ctrl+C 或 kill 进程）")
    print("2. 等待 5 秒")
    print("3. 重新启动 Celery Worker")
    print("4. 然后按 Enter 键继续测试...")
    print("\n" + "=" * 70)
    
    input("按 Enter 键继续...")
    
    print("\n[步骤 4] 验证任务恢复")
    print("      等待 10 秒后查询任务状态...")
    time.sleep(10)
    
    status = query_task_status(celery_task_id)
    if not status:
        print_result("任务恢复验证", False, "无法查询任务状态")
        return False
    
    final_state = status["state"]
    ready = status["ready"]
    successful = status["successful"]
    
    print(f"      最终状态: {final_state}")
    print(f"      是否完成: {ready}")
    if successful is not None:
        print(f"      是否成功: {successful}")
    
    # 验证结果
    if ready:
        if successful:
            print_result("任务恢复验证", True, "任务已成功恢复并完成")
        else:
            print_result("任务恢复验证", False, "任务已恢复但执行失败")
    elif final_state in ["PENDING", "STARTED", "RETRY"]:
        print_result("任务恢复验证", True, f"任务已恢复，当前状态: {final_state}")
    else:
        print_result("任务恢复验证", False, f"任务状态异常: {final_state}")
    
    return True


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  Celery 任务恢复机制测试")
    print("=" * 70)
    print(f"\nAPI 地址: {API_BASE_URL}")
    print(f"测试用户名: {TEST_USERNAME}")
    
    # 1. 登录
    if not login():
        print("\n[ERROR] 无法登录，测试终止")
        return False
    
    # 2. 测试任务恢复
    success = test_task_recovery()
    
    # 总结
    print_header("测试总结")
    print_result("登录", True)
    print_result("任务恢复验证", success)
    
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

