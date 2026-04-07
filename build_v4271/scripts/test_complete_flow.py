#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整流程测试脚本（包含Worker验证）

测试数据同步的完整流程，包括：
1. 提交任务
2. 检查Worker状态
3. 查询进度
4. 验证结果
"""

import sys
from pathlib import Path
import time
import requests
from datetime import datetime

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

BASE_URL = "http://localhost:8001/api"


def check_services():
    """检查所有服务状态"""
    print("=" * 80)
    print("服务状态检查")
    print("=" * 80)
    
    results = {}
    
    # 1. 检查Redis
    print("\n[1] Redis服务...")
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
        r.ping()
        print("  ✅ Redis连接成功")
        results['redis'] = True
        
        # 检查队列
        queue_len = r.llen('data_sync')
        print(f"     data_sync队列长度: {queue_len}")
        results['redis_queue'] = queue_len
    except Exception as e:
        print(f"  ❌ Redis连接失败: {e}")
        results['redis'] = False
    
    # 2. 检查API
    print("\n[2] API服务...")
    try:
        response = requests.get(f"{BASE_URL.replace('/api', '')}/health", timeout=5)
        if response.status_code == 200:
            print("  ✅ API服务正常运行")
            results['api'] = True
        else:
            print(f"  ❌ API服务异常: {response.status_code}")
            results['api'] = False
    except Exception as e:
        print(f"  ❌ API服务连接失败: {e}")
        results['api'] = False
    
    # 3. 检查Celery Worker
    print("\n[3] Celery Worker...")
    try:
        import subprocess
        result = subprocess.run(
            ["python", "-m", "celery", "-A", "backend.celery_app", "inspect", "active"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(root_dir)
        )
        
        if result.returncode == 0:
            print("  ✅ Celery Worker正在运行")
            print(f"     输出: {result.stdout[:200]}")
            results['worker'] = True
        else:
            print("  ⚠️  Celery Worker未运行或未响应")
            print(f"     错误: {result.stderr[:200]}")
            results['worker'] = False
    except Exception as e:
        print(f"  ⚠️  无法检查Worker状态: {e}")
        results['worker'] = False
    
    return results


def test_batch_sync():
    """测试批量同步"""
    print("\n" + "=" * 80)
    print("批量同步测试")
    print("=" * 80)
    
    try:
        payload = {
            "platform": "shopee",
            "domains": ["orders"],
            "limit": 3,  # 只测试3个文件
            "only_with_template": True,
            "allow_quarantine": True
        }
        
        print(f"\n提交批量同步任务...")
        print(f"  平台: {payload['platform']}")
        print(f"  数据域: {payload['domains']}")
        print(f"  文件数限制: {payload['limit']}")
        
        response = requests.post(
            f"{BASE_URL}/data-sync/batch",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                task_id = data.get("task_id")
                celery_task_id = data.get("celery_task_id")
                total_files = data.get("total_files", 0)
                
                print(f"\n  ✅ 任务提交成功")
                print(f"     Task ID: {task_id}")
                print(f"     Celery Task ID: {celery_task_id}")
                print(f"     总文件数: {total_files}")
                
                return task_id, celery_task_id, total_files
            else:
                print(f"  ❌ 任务提交失败: {data.get('message')}")
                return None, None, 0
        else:
            print(f"  ❌ API请求失败: {response.status_code}")
            print(f"     响应: {response.text[:500]}")
            return None, None, 0
            
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        import traceback
        traceback.print_exc()
        return None, None, 0


def monitor_progress(task_id, max_wait=60):
    """监控任务进度"""
    print(f"\n监控任务进度 (Task ID: {task_id})...")
    print("  等待Worker处理任务...")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(
                f"{BASE_URL}/data-sync/progress/{task_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    progress_data = data.get("data", {})
                    status = progress_data.get("status", "unknown")
                    processed = progress_data.get("processed_files", 0)
                    total = progress_data.get("total_files", 0)
                    percentage = progress_data.get("file_progress", 0)
                    current_file = progress_data.get("current_file", "")
                    
                    # 只在状态变化时打印
                    if status != last_status:
                        print(f"\n  状态更新: {status}")
                        last_status = status
                    
                    if status == "processing":
                        print(f"    进度: {processed}/{total} ({percentage:.1f}%) - 当前文件: {current_file}")
                    elif status in ["completed", "failed"]:
                        print(f"\n  ✅ 任务完成: {status}")
                        print(f"    处理文件数: {processed}/{total}")
                        print(f"    成功行数: {progress_data.get('valid_rows', 0)}")
                        print(f"    隔离行数: {progress_data.get('quarantined_rows', 0)}")
                        print(f"    错误行数: {progress_data.get('error_rows', 0)}")
                        
                        # 检查质量检查结果
                        quality_check = progress_data.get("task_details", {}).get("quality_check")
                        if quality_check:
                            print(f"\n  数据质量检查结果:")
                            print(f"    平均质量评分: {quality_check.get('avg_quality_score', 0):.2f}")
                            print(f"    检查平台数: {quality_check.get('checked_platforms', 0)}")
                        
                        return progress_data
                    
            elif response.status_code == 404:
                print(f"  ⚠️  任务不存在（可能已完成）")
                return None
                
        except Exception as e:
            print(f"  ⚠️  查询异常: {e}")
        
        time.sleep(2)
    
    print(f"\n  ⚠️  监控超时（{max_wait}秒）")
    return None


def main():
    """主函数"""
    print("=" * 80)
    print("数据同步完整流程测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API地址: {BASE_URL}")
    print("=" * 80)
    
    # 1. 检查服务状态
    service_status = check_services()
    
    if not service_status.get('redis'):
        print("\n❌ Redis服务未运行，请先启动Redis")
        print("   运行: docker-compose up -d redis")
        return False
    
    if not service_status.get('api'):
        print("\n❌ API服务未运行，请先启动后端服务")
        print("   运行: python run.py --backend-only")
        return False
    
    # 2. 提交批量同步任务
    task_id, celery_task_id, total_files = test_batch_sync()
    
    if not task_id:
        print("\n❌ 任务提交失败")
        return False
    
    # 3. 监控任务进度
    if service_status.get('worker'):
        print("\n✅ Celery Worker正在运行，任务应该会自动处理")
    else:
        print("\n⚠️  Celery Worker未运行，任务将保持pending状态")
        print("   请启动Worker: python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync --pool=solo")
    
    progress_data = monitor_progress(task_id, max_wait=120)
    
    # 4. 输出总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    
    if progress_data:
        print("✅ 完整流程测试成功")
        print(f"   任务状态: {progress_data.get('status')}")
        print(f"   处理文件数: {progress_data.get('processed_files', 0)}/{progress_data.get('total_files', 0)}")
    else:
        print("⚠️  任务未完成（可能Worker未运行）")
        print("   请启动Celery Worker后重新测试")
    
    print("=" * 80)
    
    return progress_data is not None


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

