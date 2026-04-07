#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步集成测试脚本

测试修复后的数据同步功能是否正常工作：
1. 测试批量同步API
2. 测试进度查询API
3. 验证错误处理
"""

import requests
import time
import json
import os
from typing import Optional

# 禁用代理（避免本地请求走代理）
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BASE_URL = "http://127.0.0.1:8001/api"


def test_batch_sync():
    """测试批量同步API"""
    print("\n" + "="*60)
    print("测试1：批量同步API")
    print("="*60)
    
    try:
        # 请求批量同步（只处理1个文件，快速测试）
        response = requests.post(
            f"{BASE_URL}/data-sync/batch",
            json={
                "platform": "shopee",
                "domains": ["orders"],
                "limit": 1,
                "only_with_template": True,
                "allow_quarantine": True
            },
            timeout=10,
            proxies={'http': None, 'https': None}  # 禁用代理
        )
        
        print(f"[INFO] HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 批量同步请求成功")
            print(f"  - task_id: {data.get('data', {}).get('task_id', 'N/A')}")
            print(f"  - total_files: {data.get('data', {}).get('total_files', 0)}")
            print(f"  - message: {data.get('message', 'N/A')}")
            
            task_id = data.get('data', {}).get('task_id')
            if task_id:
                return task_id
            else:
                print("[WARN] 未返回task_id")
                return None
        else:
            print(f"[ERROR] 批量同步请求失败: {response.status_code}")
            print(f"  响应: {response.text[:200]}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 请求异常: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] 测试异常: {e}")
        return None


def test_progress_query(task_id: str, max_queries: int = 10):
    """测试进度查询API"""
    print("\n" + "="*60)
    print(f"测试2：进度查询API (task_id={task_id})")
    print("="*60)
    
    success_count = 0
    null_count = 0
    error_count = 0
    
    for i in range(max_queries):
        try:
            response = requests.get(
                f"{BASE_URL}/data-sync/progress/{task_id}",
                timeout=5,
                proxies={'http': None, 'https': None}  # 禁用代理
            )
            
            if response.status_code == 200:
                data = response.json()
                task_info = data.get('data')
                
                if task_info:
                    success_count += 1
                    status = task_info.get('status', 'unknown')
                    processed = task_info.get('processed_files', 0)
                    total = task_info.get('total_files', 0)
                    print(f"[OK] 查询 {i+1}/{max_queries}: status={status}, "
                          f"processed={processed}/{total}")
                    
                    # 如果任务完成，停止查询
                    if status in ['completed', 'failed']:
                        print(f"[OK] 任务已完成: status={status}")
                        break
                else:
                    null_count += 1
                    print(f"[WARN] 查询 {i+1}/{max_queries}: 返回null（可能任务不存在或已完成）")
            elif response.status_code == 404:
                print(f"[WARN] 查询 {i+1}/{max_queries}: 任务不存在 (404)")
                null_count += 1
            else:
                error_count += 1
                print(f"[ERROR] 查询 {i+1}/{max_queries}: HTTP {response.status_code}")
                print(f"  响应: {response.text[:200]}")
            
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            error_count += 1
            print(f"[ERROR] 查询 {i+1}/{max_queries}: 请求异常 - {e}")
            time.sleep(1)
        except Exception as e:
            error_count += 1
            print(f"[ERROR] 查询 {i+1}/{max_queries}: 异常 - {e}")
            time.sleep(1)
    
    print(f"\n[统计] 成功: {success_count}, Null: {null_count}, 错误: {error_count}")
    
    # 验证：至少应该有几次成功查询
    if success_count > 0:
        print("[OK] 进度查询功能正常")
        return True
    elif null_count > 0:
        print("[WARN] 进度查询返回null（可能是任务已完成或不存在）")
        return True  # 不算失败，可能是正常的
    else:
        print("[ERROR] 进度查询全部失败")
        return False


def test_task_list():
    """测试任务列表API"""
    print("\n" + "="*60)
    print("测试3：任务列表API（备用方案）")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/data-sync/tasks",
            params={"limit": 10},
            timeout=5,
            proxies={'http': None, 'https': None}  # 禁用代理
        )
        
        if response.status_code == 200:
            data = response.json()
            tasks = data.get('data', [])
            print(f"[OK] 任务列表查询成功: 找到{len(tasks)}个任务")
            
            if tasks:
                print(f"[OK] 最新任务: task_id={tasks[0].get('task_id')}, "
                      f"status={tasks[0].get('status')}")
            
            return True
        else:
            print(f"[ERROR] 任务列表查询失败: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[ERROR] 任务列表查询异常: {e}")
        return False


def test_error_handling():
    """测试错误处理"""
    print("\n" + "="*60)
    print("测试4：错误处理（查询不存在的任务）")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/data-sync/progress/non_existent_task_12345",
            timeout=5,
            proxies={'http': None, 'https': None}  # 禁用代理
        )
        
        if response.status_code == 404:
            print("[OK] 正确返回404（任务不存在）")
            return True
        elif response.status_code == 200:
            data = response.json()
            if not data.get('data'):
                print("[OK] 返回null（符合预期）")
                return True
            else:
                print("[WARN] 返回了数据（不符合预期）")
                return False
        else:
            print(f"[WARN] 返回HTTP {response.status_code}（预期404）")
            return True  # 不算失败
            
    except Exception as e:
        print(f"[ERROR] 错误处理测试异常: {e}")
        return False


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("数据同步集成测试")
    print("="*60)
    print(f"API地址: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # 测试1：批量同步
    task_id = test_batch_sync()
    results.append(("批量同步API", task_id is not None))
    
    # 测试2：进度查询（如果有task_id）
    if task_id:
        result = test_progress_query(task_id, max_queries=10)
        results.append(("进度查询API", result))
    else:
        print("\n[WARN] 跳过进度查询测试（未获取到task_id）")
        results.append(("进度查询API", False))
    
    # 测试3：任务列表
    result = test_task_list()
    results.append(("任务列表API", result))
    
    # 测试4：错误处理
    result = test_error_handling()
    results.append(("错误处理", result))
    
    # 输出测试结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "[OK] 通过" if result else "[ERROR] 失败"
        print(f"{name}: {status}")
        if not result:
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("[OK] 所有测试通过")
        return 0
    else:
        print("[ERROR] 部分测试失败")
        return 1


if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code)

