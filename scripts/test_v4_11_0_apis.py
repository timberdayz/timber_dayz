#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
v4.11.0 API测试脚本

用途：快速测试新API端点是否正常工作
"""

import sys
import requests
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:8001/api"


def test_api(method, endpoint, data=None, params=None):
    """测试API端点"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, params=params, timeout=10)
        elif method == "PUT":
            response = requests.put(url, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            return False, f"不支持的HTTP方法: {method}"
        
        if response.status_code in [200, 201]:
            return True, f"状态码: {response.status_code}"
        else:
            return False, f"状态码: {response.status_code}, 响应: {response.text[:200]}"
    except requests.exceptions.ConnectionError:
        return False, "连接失败（后端服务可能未启动）"
    except Exception as e:
        return False, f"错误: {str(e)}"


def main():
    """主测试函数"""
    print("=" * 60)
    print("v4.11.0 API端点测试")
    print("=" * 60)
    print(f"\n测试目标: {BASE_URL}")
    print("\n提示: 确保后端服务已启动 (python run.py)\n")
    
    # 测试用例
    test_cases = [
        # 销售战役管理API
        ("GET", "/sales-campaigns", None, {"page": 1, "page_size": 10}),
        ("GET", "/sales-campaigns/1", None, None),
        
        # 目标管理API
        ("GET", "/targets", None, {"page": 1, "page_size": 10}),
        ("GET", "/targets/1", None, None),
        
        # 绩效管理API
        ("GET", "/performance/config", None, {"page": 1, "page_size": 10}),
        ("GET", "/performance/scores", None, {"page": 1, "page_size": 10}),
        
        # 店铺分析API
        ("GET", "/store-analytics/health-scores", None, {"page": 1, "page_size": 10}),
        ("GET", "/store-analytics/gmv-trend", None, {"granularity": "daily"}),
        ("GET", "/store-analytics/conversion-analysis", None, {"granularity": "daily"}),
        ("GET", "/store-analytics/alerts", None, {"page": 1, "page_size": 10}),
    ]
    
    passed = 0
    failed = 0
    
    for method, endpoint, data, params in test_cases:
        success, message = test_api(method, endpoint, data, params)
        
        status = "[OK]" if success else "[FAIL]"
        print(f"{status} {method:6} {endpoint:50} - {message}")
        
        if success:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: 通过 {passed}/{len(test_cases)}, 失败 {failed}/{len(test_cases)}")
    print("=" * 60)
    
    if failed > 0:
        print("\n提示: 如果看到连接失败，请先启动后端服务:")
        print("  python run.py")
        sys.exit(1)
    else:
        print("\n所有API端点测试通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()

