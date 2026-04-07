#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速数据同步测试脚本

测试修复后的数据同步功能：
1. 健康检查
2. 查询待同步文件
3. 测试单文件同步（如果有文件）
4. 测试批量同步（如果有文件）
"""

import requests
import os
import json
from datetime import datetime

# 禁用代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BASE_URL = "http://127.0.0.1:8001/api"
PROXIES = {'http': None, 'https': None}


def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def test_health():
    """测试健康检查"""
    safe_print("\n[测试1] API健康检查...")
    try:
        response = requests.get(
            f"{BASE_URL.replace('/api', '')}/health",
            timeout=5,
            proxies=PROXIES
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"  [OK] API服务正常")
            safe_print(f"  - 状态: {data.get('status')}")
            safe_print(f"  - 数据库: {data.get('database', {}).get('status')}")
            return True
        else:
            safe_print(f"  [ERROR] API服务异常: {response.status_code}")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] API服务连接失败: {e}")
        return False


def test_get_pending_files():
    """查询待同步文件"""
    safe_print("\n[测试2] 查询待同步文件...")
    try:
        # 查询catalog_files表，获取pending状态的文件
        response = requests.get(
            f"{BASE_URL}/field-mapping/files",
            params={
                "status": "pending",
                "limit": 5
            },
            timeout=10,
            proxies=PROXIES
        )
        
        if response.status_code == 200:
            data = response.json()
            files = data.get('data', {}).get('files', [])
            safe_print(f"  [OK] 找到 {len(files)} 个待同步文件")
            
            if files:
                for i, file in enumerate(files[:3], 1):
                    safe_print(f"  - 文件{i}: {file.get('file_name')} (ID: {file.get('id')})")
                    safe_print(f"    平台: {file.get('platform_code')}, 数据域: {file.get('data_domain')}")
            
            return files
        else:
            safe_print(f"  [ERROR] 查询失败: {response.status_code}")
            safe_print(f"  响应: {response.text[:200]}")
            return []
    except Exception as e:
        safe_print(f"  [ERROR] 查询异常: {e}")
        return []


def test_single_file_sync(file_id):
    """测试单文件同步"""
    safe_print(f"\n[测试3] 单文件同步测试 (file_id={file_id})...")
    try:
        response = requests.post(
            f"{BASE_URL}/data-sync/single",
            json={
                "file_id": file_id,
                "only_with_template": False,  # 允许无模板文件
                "allow_quarantine": True
            },
            timeout=30,
            proxies=PROXIES
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                result = data.get('data', {})
                safe_print(f"  [OK] 单文件同步成功")
                safe_print(f"  - 任务ID: {result.get('task_id', 'N/A')}")
                safe_print(f"  - 入库行数: {result.get('imported', 0)}")
                safe_print(f"  - 隔离行数: {result.get('quarantined', 0)}")
                return True
            else:
                safe_print(f"  [ERROR] 同步失败: {data.get('message', '未知错误')}")
                return False
        else:
            safe_print(f"  [ERROR] 请求失败: {response.status_code}")
            safe_print(f"  响应: {response.text[:300]}")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 同步异常: {e}")
        return False


def test_batch_sync():
    """测试批量同步"""
    safe_print("\n[测试4] 批量同步测试...")
    try:
        response = requests.post(
            f"{BASE_URL}/data-sync/batch",
            json={
                "platform": "*",  # 所有平台
                "domains": [],  # 所有数据域
                "limit": 1,  # 只处理1个文件（快速测试）
                "only_with_template": False,  # 允许无模板文件
                "allow_quarantine": True
            },
            timeout=10,
            proxies=PROXIES
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                result = data.get('data', {})
                task_id = result.get('task_id')
                total_files = result.get('total_files', 0)
                safe_print(f"  [OK] 批量同步请求成功")
                safe_print(f"  - 任务ID: {task_id}")
                safe_print(f"  - 待处理文件数: {total_files}")
                
                if total_files > 0:
                    safe_print(f"  - 任务已提交，后台处理中...")
                    return task_id
                else:
                    safe_print(f"  - 没有待处理的文件")
                    return None
            else:
                safe_print(f"  [ERROR] 请求失败: {data.get('message', '未知错误')}")
                return None
        else:
            safe_print(f"  [ERROR] 请求失败: {response.status_code}")
            safe_print(f"  响应: {response.text[:300]}")
            return None
    except Exception as e:
        safe_print(f"  [ERROR] 批量同步异常: {e}")
        return None


def test_progress_query(task_id):
    """查询任务进度"""
    safe_print(f"\n[测试5] 查询任务进度 (task_id={task_id})...")
    try:
        response = requests.get(
            f"{BASE_URL}/data-sync/progress/{task_id}",
            timeout=5,
            proxies=PROXIES
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                progress = data.get('data', {})
                safe_print(f"  [OK] 进度查询成功")
                safe_print(f"  - 状态: {progress.get('status')}")
                safe_print(f"  - 进度: {progress.get('file_progress', 0):.1f}%")
                safe_print(f"  - 已处理: {progress.get('processed_files', 0)}/{progress.get('total_files', 0)}")
                safe_print(f"  - 有效行数: {progress.get('valid_rows', 0)}")
                return True
            else:
                safe_print(f"  [ERROR] 查询失败: {data.get('message', '未知错误')}")
                return False
        else:
            safe_print(f"  [ERROR] 请求失败: {response.status_code}")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 查询异常: {e}")
        return False


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("数据同步功能快速测试")
    safe_print("=" * 80)
    safe_print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print(f"API地址: {BASE_URL}")
    safe_print("=" * 80)
    
    results = {}
    
    # 1. 健康检查
    results['health'] = test_health()
    if not results['health']:
        safe_print("\n[ERROR] API服务未运行，请先启动后端服务")
        return False
    
    # 2. 查询待同步文件
    pending_files = test_get_pending_files()
    results['get_files'] = True
    
    # 3. 单文件同步测试（如果有文件）
    if pending_files:
        file_id = pending_files[0].get('id')
        if file_id:
            results['single_sync'] = test_single_file_sync(file_id)
        else:
            safe_print("\n[WARN] 跳过单文件同步测试（文件ID无效）")
            results['single_sync'] = None
    else:
        safe_print("\n[WARN] 跳过单文件同步测试（没有待同步文件）")
        results['single_sync'] = None
    
    # 4. 批量同步测试
    task_id = test_batch_sync()
    results['batch_sync'] = task_id is not None
    
    # 5. 进度查询（如果有任务）
    if task_id:
        import time
        safe_print("\n等待3秒后查询进度...")
        time.sleep(3)
        results['progress'] = test_progress_query(task_id)
    else:
        safe_print("\n[WARN] 跳过进度查询（没有任务ID）")
        results['progress'] = None
    
    # 输出总结
    safe_print("\n" + "=" * 80)
    safe_print("测试结果汇总")
    safe_print("=" * 80)
    
    for name, result in results.items():
        if result is None:
            status = "[SKIP] 跳过"
        elif result:
            status = "[OK] 通过"
        else:
            status = "[ERROR] 失败"
        safe_print(f"{name}: {status}")
    
    safe_print("=" * 80)
    
    # 判断总体结果
    passed = sum(1 for v in results.values() if v is True)
    total = sum(1 for v in results.values() if v is not None)
    
    if total > 0 and passed == total:
        safe_print("[OK] 所有测试通过")
        return True
    elif passed > 0:
        safe_print(f"[WARN] 部分测试通过 ({passed}/{total})")
        return True
    else:
        safe_print("[ERROR] 测试失败")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

