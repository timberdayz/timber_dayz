#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试Metabase性能
验证并发查询性能和响应时间

使用方法:
    python scripts/test_metabase_performance.py
"""

import sys
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_metabase_query(metabase_url: str, query: str, timeout: int = 60) -> Dict[str, Any]:
    """
    测试单个Metabase查询
    
    Args:
        metabase_url: Metabase API URL
        query: SQL查询语句
        timeout: 超时时间（秒）
    
    Returns:
        包含响应时间、状态码、错误信息的字典
    """
    start_time = time.time()
    result = {
        "query": query,
        "success": False,
        "response_time": 0,
        "status_code": None,
        "error": None
    }
    
    try:
        # 这里需要根据实际的Metabase API格式调整
        # 示例：使用Metabase API执行查询
        response = requests.post(
            f"{metabase_url}/api/dataset",
            json={"query": query},
            timeout=timeout
        )
        
        result["status_code"] = response.status_code
        result["response_time"] = time.time() - start_time
        
        if response.status_code == 200:
            result["success"] = True
        else:
            result["error"] = response.text
            
    except requests.exceptions.Timeout:
        result["error"] = f"查询超时（>{timeout}秒）"
        result["response_time"] = timeout
    except requests.exceptions.ConnectionError:
        result["error"] = "无法连接到Metabase服务"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_concurrent_queries(
    metabase_url: str = "http://localhost:8080",  # 端口从3000改为8080，避免Windows端口权限问题
    num_users: int = 10,
    queries: List[str] = None
) -> Dict[str, Any]:
    """
    测试并发查询性能
    
    Args:
        metabase_url: Metabase服务URL
        num_users: 并发用户数
        queries: 查询列表（如果为None，使用默认查询）
    
    Returns:
        测试结果字典
    """
    if queries is None:
        # 默认查询列表
        queries = [
            "SELECT COUNT(*) FROM b_class.fact_raw_data_orders_daily",
            "SELECT COUNT(*) FROM b_class.fact_raw_data_products_daily",
            "SELECT COUNT(*) FROM a_class.sales_targets_a",
            "SELECT COUNT(*) FROM core.catalog_files",
        ]
    
    results = {
        "success": True,
        "total_queries": len(queries) * num_users,
        "successful_queries": 0,
        "failed_queries": 0,
        "response_times": [],
        "errors": [],
        "concurrent_users": num_users
    }
    
    print(f"\n{'='*60}")
    print(f"Metabase并发查询性能测试")
    print(f"{'='*60}")
    print(f"Metabase URL: {metabase_url}")
    print(f"并发用户数: {num_users}")
    print(f"查询数量: {len(queries)}")
    print(f"总查询数: {results['total_queries']}")
    print()
    
    # 执行并发查询
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        # 提交所有查询任务
        futures = []
        for user_id in range(num_users):
            for query in queries:
                future = executor.submit(test_metabase_query, metabase_url, query)
                futures.append(future)
        
        # 收集结果
        for future in as_completed(futures):
            try:
                result = future.result()
                results["response_times"].append(result["response_time"])
                
                if result["success"]:
                    results["successful_queries"] += 1
                else:
                    results["failed_queries"] += 1
                    results["errors"].append({
                        "query": result["query"],
                        "error": result["error"]
                    })
                    results["success"] = False
            except Exception as e:
                results["failed_queries"] += 1
                results["errors"].append({"error": str(e)})
                results["success"] = False
    
    total_time = time.time() - start_time
    
    # 计算统计信息
    if results["response_times"]:
        results["avg_response_time"] = sum(results["response_times"]) / len(results["response_times"])
        results["min_response_time"] = min(results["response_times"])
        results["max_response_time"] = max(results["response_times"])
        results["total_time"] = total_time
        results["queries_per_second"] = results["total_queries"] / total_time if total_time > 0 else 0
    else:
        results["avg_response_time"] = 0
        results["min_response_time"] = 0
        results["max_response_time"] = 0
        results["total_time"] = total_time
        results["queries_per_second"] = 0
    
    # 输出结果
    print(f"测试完成时间: {total_time:.2f} 秒")
    print(f"成功查询: {results['successful_queries']}/{results['total_queries']}")
    print(f"失败查询: {results['failed_queries']}/{results['total_queries']}")
    print()
    
    if results["response_times"]:
        print(f"响应时间统计:")
        print(f"  平均: {results['avg_response_time']:.3f} 秒")
        print(f"  最小: {results['min_response_time']:.3f} 秒")
        print(f"  最大: {results['max_response_time']:.3f} 秒")
        print(f"  吞吐量: {results['queries_per_second']:.2f} 查询/秒")
        print()
    
    if results["errors"]:
        print(f"错误信息（前5个）:")
        for error in results["errors"][:5]:
            print(f"  [ERROR] {error.get('query', 'Unknown')}: {error.get('error', 'Unknown error')}")
        print()
    
    # 性能评估
    if results["avg_response_time"] < 1.0:
        print("[OK] 性能优秀：平均响应时间 < 1秒")
    elif results["avg_response_time"] < 3.0:
        print("[OK] 性能良好：平均响应时间 < 3秒")
    elif results["avg_response_time"] < 5.0:
        print("[WARN] 性能一般：平均响应时间 < 5秒，建议优化")
    else:
        print("[ERROR] 性能较差：平均响应时间 >= 5秒，需要优化")
        results["success"] = False
    
    if results["successful_queries"] / results["total_queries"] >= 0.95:
        print("[OK] 成功率 >= 95%")
    else:
        print(f"[WARN] 成功率: {results['successful_queries']/results['total_queries']*100:.1f}%")
        results["success"] = False
    
    return results


def test_metabase_health(metabase_url: str = "http://localhost:8080") -> bool:  # 端口从3000改为8080
    """
    测试Metabase服务健康状态
    
    Args:
        metabase_url: Metabase服务URL
    
    Returns:
        服务是否健康
    """
    try:
        response = requests.get(f"{metabase_url}/api/health", timeout=5)
        if response.status_code == 200:
            logger.info(f"[OK] Metabase服务健康检查通过")
            return True
        else:
            logger.warning(f"[WARN] Metabase服务健康检查失败: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        logger.error(f"[ERROR] 无法连接到Metabase服务: {metabase_url}")
        print(f"\n[ERROR] 无法连接到Metabase服务")
        print(f"请确保Metabase服务正在运行: {metabase_url}")
        print(f"启动命令: docker-compose -f docker-compose.metabase.yml up -d")
        return False
    except Exception as e:
        logger.error(f"[ERROR] Metabase健康检查失败: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试Metabase性能")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="Metabase服务URL（默认: http://localhost:8080，端口从3000改为8080避免Windows端口权限问题）"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=10,
        help="并发用户数（默认: 10）"
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="仅执行健康检查"
    )
    
    args = parser.parse_args()
    
    # 健康检查
    if not test_metabase_health(args.url):
        print("\n[ERROR] Metabase服务不可用，无法执行性能测试")
        sys.exit(1)
    
    if args.health_only:
        print("\n[OK] Metabase服务健康检查通过")
        sys.exit(0)
    
    # 性能测试
    results = test_concurrent_queries(
        metabase_url=args.url,
        num_users=args.users
    )
    
    if results["success"]:
        print("\n[OK] Metabase性能测试通过！")
        sys.exit(0)
    else:
        print("\n[WARN] Metabase性能测试部分失败，请检查错误信息")
        sys.exit(1)

