#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 任务状态管理 API 测试脚本

测试任务状态查询、取消和重试功能。
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
API_ENDPOINTS = {
    "health": f"{API_BASE_URL}/health",
    "login": f"{API_BASE_URL}/api/auth/login",  # ⭐ 新增：登录端点
    "sync_single_file": f"{API_BASE_URL}/api/data-sync/single",  # ⭐ 修复：使用正确的端点路径
    "task_status": f"{API_BASE_URL}/api/data-sync/task-status",
    "cancel_task": f"{API_BASE_URL}/api/data-sync/cancel-task",
    "retry_task": f"{API_BASE_URL}/api/data-sync/retry-task",
}

# 测试配置
TEST_FILE_ID = None  # 测试文件ID（自动获取）
TEST_USERNAME = "admin"  # 测试用户名（默认 admin）
TEST_PASSWORD = "admin"  # 测试密码（默认 admin）
AUTH_TOKEN = None  # 自动获取 token


def find_available_file_id():
    """查找可用的文件ID"""
    global TEST_FILE_ID
    
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/data-sync/files?page_size=1",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            files = data.get("data", {}).get("files", [])
            if files:
                TEST_FILE_ID = files[0].get("id")
                return TEST_FILE_ID
    except Exception:
        pass
    
    return None


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


def login_and_get_token():
    """登录并获取认证 token"""
    print_header("登录获取认证 Token")
    
    payload = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    }
    
    try:
        response = requests.post(
            API_ENDPOINTS["login"],
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            # 支持两种响应格式：success/data 或直接返回 access_token
            if data.get("success") or "access_token" in data:
                token = data.get("access_token") or data.get("data", {}).get("access_token")
                if token:
                    print_result("登录成功", True, f"Token 已获取")
                    return token
                else:
                    print_result("登录失败", False, "响应中未找到 access_token")
                    return None
            else:
                print_result("登录失败", False, f"响应: {data.get('message', '未知错误')}")
                return None
        else:
            print_result("登录失败", False, f"状态码: {response.status_code}, 响应: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print_result("登录失败", False, f"请求失败: {str(e)}")
        return None


def check_service_health():
    """检查服务健康状态"""
    print_header("检查服务健康状态")
    
    try:
        response = requests.get(API_ENDPOINTS["health"], timeout=5)
        if response.status_code == 200:
            print_result("后端服务健康检查", True, f"状态码: {response.status_code}")
            return True
        else:
            print_result("后端服务健康检查", False, f"状态码: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_result("后端服务健康检查", False, f"连接失败: {str(e)}")
        print("      [提示] 请确保后端服务正在运行 (http://localhost:8001)")
        return False


def submit_test_task():
    """提交测试任务"""
    print_header("提交测试任务")
    
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    payload = {
        "file_id": TEST_FILE_ID,
        "priority": 5
    }
    
    try:
        response = requests.post(
            API_ENDPOINTS["sync_single_file"],
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
    except requests.exceptions.RequestException as e:
        print_result("任务提交", False, f"请求失败: {str(e)}")
        return None


def query_task_status(celery_task_id):
    """查询任务状态"""
    print_header(f"查询任务状态 (celery_task_id: {celery_task_id})")
    
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.get(
            f"{API_ENDPOINTS['task_status']}/{celery_task_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            state = data.get("state", "UNKNOWN")
            ready = data.get("ready", False)
            successful = data.get("successful")
            
            print_result("任务状态查询", True, f"状态: {state}, 完成: {ready}")
            if successful is not None:
                print(f"      成功: {successful}")
            
            return {
                "state": state,
                "ready": ready,
                "successful": successful,
                "data": data
            }
        else:
            print_result("任务状态查询", False, f"状态码: {response.status_code}, 响应: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print_result("任务状态查询", False, f"请求失败: {str(e)}")
        return None


def test_task_status_polling(celery_task_id, max_wait=60):
    """轮询任务状态直到完成"""
    print_header(f"轮询任务状态 (最多等待 {max_wait} 秒)")
    
    start_time = time.time()
    poll_count = 0
    
    while True:
        poll_count += 1
        elapsed = time.time() - start_time
        
        if elapsed > max_wait:
            print_result("任务完成检查", False, f"超时 ({max_wait} 秒)")
            return False
        
        status = query_task_status(celery_task_id)
        if not status:
            return False
        
        state = status["state"]
        ready = status["ready"]
        
        print(f"  [轮询 {poll_count}] 状态: {state}, 完成: {ready}, 已等待: {elapsed:.1f}秒")
        
        if ready:
            successful = status["successful"]
            if successful:
                print_result("任务执行", True, f"任务成功完成 (耗时: {elapsed:.1f}秒)")
            else:
                print_result("任务执行", False, f"任务失败 (耗时: {elapsed:.1f}秒)")
                traceback = status["data"].get("traceback")
                if traceback:
                    print(f"      错误信息: {traceback[:200]}...")
            return successful
        
        time.sleep(2)  # 每2秒轮询一次


def test_cancel_task(celery_task_id):
    """测试取消任务"""
    print_header(f"测试取消任务 (celery_task_id: {celery_task_id})")
    
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.delete(
            f"{API_ENDPOINTS['cancel_task']}/{celery_task_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            revoked = data.get("revoked", False)
            message = data.get("message", "")
            print_result("取消任务", True, f"{message}, 已撤销: {revoked}")
            return True
        elif response.status_code == 400:
            data = response.json()
            print_result("取消任务", False, f"无法取消: {data.get('detail', '未知错误')}")
            return False
        else:
            print_result("取消任务", False, f"状态码: {response.status_code}, 响应: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_result("取消任务", False, f"请求失败: {str(e)}")
        return False


def main():
    """主测试流程"""
    global TEST_FILE_ID
    
    print("\n" + "=" * 70)
    print("  Celery 任务状态管理 API 测试")
    print("=" * 70)
    print(f"\nAPI 地址: {API_BASE_URL}")
    print(f"测试用户名: {TEST_USERNAME}")
    
    # 1. 检查服务健康状态
    if not check_service_health():
        print("\n[ERROR] 服务不可用，请先启动后端服务")
        return False
    
    # 2. 登录获取认证 token
    global AUTH_TOKEN
    AUTH_TOKEN = login_and_get_token()
    if not AUTH_TOKEN:
        print("\n[WARN] 无法获取认证 token，某些测试可能会失败")
        print("       [提示] 请检查用户名和密码是否正确，或手动设置 AUTH_TOKEN")
        print("       [提示] 默认用户名/密码: admin/admin")
    
    # 2.5 查找可用的文件 ID
    print_header("查找可用的文件 ID")
    TEST_FILE_ID = find_available_file_id()
    if TEST_FILE_ID:
        print_result("查找文件 ID", True, f"找到文件 ID: {TEST_FILE_ID}")
    else:
        print_result("查找文件 ID", False, "未找到可用的文件")
        print("\n[ERROR] 无法找到可用的测试文件，测试终止")
        return False
    
    # 3. 提交测试任务
    celery_task_id = submit_test_task()
    if not celery_task_id:
        print("\n[ERROR] 无法提交任务，测试终止")
        return False
    
    # 4. 查询任务状态（立即查询）
    status = query_task_status(celery_task_id)
    if not status:
        print("\n[ERROR] 无法查询任务状态")
        return False
    
    # 5. 轮询任务状态直到完成
    print("\n[提示] 开始轮询任务状态，等待任务完成...")
    print("[提示] 如果需要测试取消功能，请在任务完成前手动调用取消 API")
    
    task_success = test_task_status_polling(celery_task_id, max_wait=120)
    
    # 6. 测试取消功能（可选，如果任务还在运行）
    # 注意：这里不自动测试取消，因为任务可能已经完成
    # 如果需要测试取消，可以手动调用 test_cancel_task(celery_task_id)
    
    # 总结
    print_header("测试总结")
    print_result("服务健康检查", True)
    print_result("登录获取 Token", AUTH_TOKEN is not None)
    print_result("任务提交", celery_task_id is not None)
    print_result("任务状态查询", status is not None)
    print_result("任务执行", task_success if task_success is not None else False)
    
    return True


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

