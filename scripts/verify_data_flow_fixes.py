#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证前后端数据流转修复脚本

验证内容：
1. API响应格式是否正确（success字段、data字段）
2. 错误处理是否正确（error_response格式、recovery_suggestion）
3. 请求ID是否正确传递（X-Request-ID头）
4. 分页响应格式是否正确
"""

import sys
import requests
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:8001"


def test_health_check():
    """测试健康检查端点"""
    print("\n[测试1] 健康检查端点")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        print(f"  状态码: {response.status_code}")
        print(f"  响应头 X-Request-ID: {response.headers.get('X-Request-ID', '未找到')}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"  响应格式: {list(data.keys())}")
            return True
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def test_success_response_format():
    """测试成功响应格式"""
    print("\n[测试2] 成功响应格式")
    try:
        # 测试一个简单的API端点
        response = requests.get(f"{BASE_URL}/api/products/products?page=1&page_size=10", timeout=10)
        print(f"  状态码: {response.status_code}")
        print(f"  响应头 X-Request-ID: {response.headers.get('X-Request-ID', '未找到')}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"  响应字段: {list(data.keys())}")
            
            # 验证响应格式
            checks = {
                "success字段存在": "success" in data,
                "success为True": data.get("success") == True,
                "data字段存在": "data" in data,
                "timestamp字段存在": "timestamp" in data,
                "request_id字段存在": "request_id" in data,
            }
            
            for check_name, check_result in checks.items():
                status = "✓" if check_result else "✗"
                print(f"    {status} {check_name}: {check_result}")
            
            return all(checks.values())
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def test_error_response_format():
    """测试错误响应格式"""
    print("\n[测试3] 错误响应格式")
    try:
        # 测试一个不存在的资源（应该返回404错误）
        response = requests.get(f"{BASE_URL}/api/products/products/999999999", timeout=10)
        print(f"  状态码: {response.status_code}")
        print(f"  响应头 X-Request-ID: {response.headers.get('X-Request-ID', '未找到')}")
        
        if response.status_code in [200, 404]:
            data = response.json()
            print(f"  响应字段: {list(data.keys())}")
            
            # 验证错误响应格式
            checks = {
                "success字段存在": "success" in data,
                "success为False": data.get("success") == False,
                "error字段存在": "error" in data,
                "message字段存在": "message" in data,
                "timestamp字段存在": "timestamp" in data,
                "request_id字段存在": "request_id" in data,
            }
            
            if "error" in data:
                error = data["error"]
                print(f"  错误对象字段: {list(error.keys())}")
                checks["error.code存在"] = "code" in error
                checks["error.type存在"] = "type" in error
            
            for check_name, check_result in checks.items():
                status = "✓" if check_result else "✗"
                print(f"    {status} {check_name}: {check_result}")
            
            return all(checks.values())
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def test_pagination_response_format():
    """测试分页响应格式"""
    print("\n[测试4] 分页响应格式")
    try:
        response = requests.get(f"{BASE_URL}/api/products/products?page=1&page_size=5", timeout=10)
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 检查是否有pagination字段（旧格式）或扁平格式（新格式）
            has_pagination = "pagination" in data
            has_flat_format = all(key in data for key in ["total", "page", "page_size"])
            
            print(f"  分页格式: {'嵌套格式(pagination)' if has_pagination else '扁平格式' if has_flat_format else '未找到'}")
            
            if has_pagination:
                pagination = data["pagination"]
                print(f"  分页字段: {list(pagination.keys())}")
                checks = {
                    "page存在": "page" in pagination,
                    "page_size存在": "page_size" in pagination,
                    "total存在": "total" in pagination,
                    "total_pages存在": "total_pages" in pagination,
                }
            elif has_flat_format:
                checks = {
                    "page存在": "page" in data,
                    "page_size存在": "page_size" in data,
                    "total存在": "total" in data,
                }
            else:
                checks = {"分页字段": False}
            
            for check_name, check_result in checks.items():
                status = "✓" if check_result else "✗"
                print(f"    {status} {check_name}: {check_result}")
            
            return all(checks.values())
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def test_request_id_consistency():
    """测试请求ID一致性"""
    print("\n[测试5] 请求ID一致性")
    try:
        response = requests.get(f"{BASE_URL}/api/products/products?page=1&page_size=1", timeout=10)
        print(f"  状态码: {response.status_code}")
        
        header_request_id = response.headers.get("X-Request-ID")
        print(f"  响应头 X-Request-ID: {header_request_id}")
        
        if response.status_code == 200:
            data = response.json()
            body_request_id = data.get("request_id")
            print(f"  响应体 request_id: {body_request_id}")
            
            if header_request_id and body_request_id:
                match = header_request_id == body_request_id
                print(f"  ✓ 请求ID一致: {match}")
                return match
            else:
                print(f"  ✗ 请求ID缺失")
                return False
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("前后端数据流转修复验证脚本")
    print("=" * 60)
    print(f"\n测试目标: {BASE_URL}")
    print("请确保后端服务已启动（python run.py）")
    
    results = []
    
    # 运行所有测试
    results.append(("健康检查", test_health_check()))
    results.append(("成功响应格式", test_success_response_format()))
    results.append(("错误响应格式", test_error_response_format()))
    results.append(("分页响应格式", test_pagination_response_format()))
    results.append(("请求ID一致性", test_request_id_consistency()))
    
    # 输出总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status} - {test_name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n✓ 所有测试通过！数据流转修复验证成功。")
        return 0
    else:
        print(f"\n✗ {total - passed} 个测试失败，请检查修复。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

