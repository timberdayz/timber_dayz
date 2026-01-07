#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发任务处理问题调试脚本

调查并发任务失败的根本原因。
"""

import sys
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# API 配置
API_BASE_URL = "http://localhost:8001"
API_ENDPOINTS = {
    "login": f"{API_BASE_URL}/api/auth/login",
    "sync_single_file": f"{API_BASE_URL}/api/data-sync/single",
}

# 测试配置
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin"
AUTH_TOKEN = None


def login_and_get_token():
    """登录并获取认证 token"""
    global AUTH_TOKEN
    
    payload = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "remember_me": True
    }
    
    try:
        response = requests.post(API_ENDPOINTS["login"], json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            AUTH_TOKEN = data.get("access_token")
            return AUTH_TOKEN
    except Exception as e:
        print(f"[ERROR] 登录失败: {e}")
    
    return None


def find_available_file_ids(count: int = 10):
    """查找可用的文件ID列表"""
    headers = {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/data-sync/files?page_size={count}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            files = data.get("data", {}).get("files", [])
            return [f.get("id") for f in files if f.get("id")]
    except Exception as e:
        print(f"[ERROR] 查找文件失败: {e}")
    
    return []


def submit_task_detailed(file_id: int, task_num: int):
    """提交任务并返回详细信息"""
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    payload = {
        "file_id": file_id,
        "priority": 5
    }
    
    start_time = time.perf_counter()
    try:
        response = requests.post(
            API_ENDPOINTS["sync_single_file"],
            json=payload,
            headers=headers,
            timeout=10
        )
        end_time = time.perf_counter()
        submit_time = (end_time - start_time) * 1000
        
        result = {
            "task_num": task_num,
            "file_id": file_id,
            "status_code": response.status_code,
            "submit_time_ms": submit_time,
            "timestamp": time.time()
        }
        
        if response.status_code == 200:
            data = response.json()
            result["success"] = data.get("success", False)
            result["response_data"] = data
            
            if data.get("success"):
                result["celery_task_id"] = data.get("data", {}).get("celery_task_id")
                result["task_id"] = data.get("data", {}).get("task_id")
            else:
                # 提取错误信息
                error_info = data.get("error", {})
                result["error"] = {
                    "code": error_info.get("code"),
                    "type": error_info.get("type"),
                    "detail": error_info.get("detail"),
                    "message": data.get("message")
                }
        else:
            result["success"] = False
            try:
                error_data = response.json()
                result["error"] = {
                    "status_code": response.status_code,
                    "message": error_data.get("message", error_data.get("error", {}).get("detail", response.text[:200]))
                }
            except:
                result["error"] = {
                    "status_code": response.status_code,
                    "message": response.text[:200]
                }
        
        return result
    except Exception as e:
        end_time = time.perf_counter()
        submit_time = (end_time - start_time) * 1000
        return {
            "task_num": task_num,
            "file_id": file_id,
            "success": False,
            "error": {"exception": str(e)},
            "submit_time_ms": submit_time,
            "timestamp": time.time()
        }


def test_concurrent_submission(num_concurrent: int = 5):
    """测试并发提交任务"""
    print("=" * 70)
    print(f"并发任务提交测试（{num_concurrent} 个并发任务）")
    print("=" * 70)
    
    # 1. 登录
    token = login_and_get_token()
    if not token:
        print("[ERROR] 无法获取认证 token")
        return
    
    # 2. 查找文件
    file_ids = find_available_file_ids(num_concurrent)
    if not file_ids:
        print("[ERROR] 未找到可用的测试文件")
        return
    
    print(f"\n[INFO] 找到 {len(file_ids)} 个文件")
    print(f"[INFO] 将并发提交 {min(num_concurrent, len(file_ids))} 个任务\n")
    
    # 3. 并发提交任务
    start_time = time.perf_counter()
    results = []
    
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = {
            executor.submit(submit_task_detailed, file_id, i+1): (file_id, i+1)
            for i, file_id in enumerate(file_ids[:num_concurrent])
        }
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            
            # 实时打印结果
            if result.get("success"):
                print(f"[OK] 任务 {result['task_num']} 提交成功 (file_id={result['file_id']}, "
                      f"time={result['submit_time_ms']:.2f}ms, "
                      f"celery_task_id={result.get('celery_task_id', 'N/A')[:8]}...)")
            else:
                error = result.get("error", {})
                print(f"[FAIL] 任务 {result['task_num']} 提交失败 (file_id={result['file_id']}, "
                      f"status_code={result.get('status_code', 'N/A')}, "
                      f"error={error.get('message', error.get('detail', error.get('exception', 'Unknown')))})")
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    # 4. 分析结果
    print("\n" + "=" * 70)
    print("结果分析")
    print("=" * 70)
    
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    print(f"\n总任务数: {len(results)}")
    print(f"成功: {len(successful)}")
    print(f"失败: {len(failed)}")
    print(f"总耗时: {total_time:.2f}秒")
    
    if successful:
        avg_time = sum(r["submit_time_ms"] for r in successful) / len(successful)
        print(f"平均提交时间: {avg_time:.2f}ms")
    
    # 5. 详细错误分析
    if failed:
        print("\n" + "-" * 70)
        print("失败任务详细分析")
        print("-" * 70)
        
        # 按错误类型分组
        error_groups = {}
        for r in failed:
            error = r.get("error", {})
            error_key = (
                r.get("status_code", "N/A"),
                error.get("code", error.get("type", "Unknown"))
            )
            if error_key not in error_groups:
                error_groups[error_key] = []
            error_groups[error_key].append(r)
        
        for (status_code, error_code), group in error_groups.items():
            print(f"\n错误类型: HTTP {status_code}, Code {error_code} ({len(group)} 个)")
            for r in group[:3]:  # 只显示前3个
                error = r.get("error", {})
                print(f"  - 任务 {r['task_num']} (file_id={r['file_id']}): "
                      f"{error.get('message', error.get('detail', error.get('exception', 'Unknown')))}")
            if len(group) > 3:
                print(f"  ... 还有 {len(group) - 3} 个相同错误")
        
        # 检查是否是配额限制
        quota_errors = [r for r in failed if r.get("status_code") == 429]
        if quota_errors:
            print(f"\n[WARN] 发现 {len(quota_errors)} 个配额限制错误 (429)")
            print("      这可能是由于用户任务配额限制导致的")
        
        # 检查时间分布
        if len(failed) > 1:
            timestamps = [r["timestamp"] for r in failed]
            time_diff = max(timestamps) - min(timestamps)
            print(f"\n[INFO] 失败任务时间分布: {time_diff*1000:.2f}ms")
            if time_diff < 0.1:
                print("       [提示] 任务几乎同时提交，可能存在竞态条件")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("并发任务处理问题调试")
    print("=" * 70)
    
    # 测试不同并发数
    for num_concurrent in [3, 5, 10]:
        print(f"\n\n{'='*70}")
        print(f"测试并发数: {num_concurrent}")
        print(f"{'='*70}\n")
        test_concurrent_submission(num_concurrent)
        
        # 等待一段时间再测试下一个
        if num_concurrent < 10:
            print("\n[INFO] 等待 5 秒后继续下一个测试...")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

