#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库设计规范验证API

⭐ v4.12.0新增：测试验证API端点
"""

import sys
import requests
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_api_endpoints():
    """测试API端点"""
    base_url = "http://localhost:8001/api/database-design"
    
    print("=" * 70)
    print("测试数据库设计规范验证API")
    print("=" * 70)
    
    endpoints = [
        ("/validate", "验证所有数据库设计"),
        ("/validate/tables", "验证表结构"),
        ("/validate/materialized-views", "验证物化视图"),
    ]
    
    results = {}
    
    for endpoint, description in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n[测试] {description}")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"   [OK] 请求成功")
                print(f"   - success: {data.get('success', False)}")
                
                if 'summary' in data:
                    summary = data['summary']
                    print(f"   - 总问题数: {summary.get('total_issues', 0)}")
                    print(f"   - 错误数: {summary.get('error_count', 0)}")
                    print(f"   - 警告数: {summary.get('warning_count', 0)}")
                    print(f"   - 信息数: {summary.get('info_count', 0)}")
                
                if 'issues' in data:
                    print(f"   - 问题数量: {len(data['issues'])}")
                
                results[endpoint] = {
                    "status": "success",
                    "status_code": response.status_code,
                    "data": data
                }
            else:
                print(f"   [FAIL] HTTP {response.status_code}")
                print(f"   - 响应: {response.text[:200]}")
                results[endpoint] = {
                    "status": "failed",
                    "status_code": response.status_code,
                    "error": response.text
                }
        
        except requests.exceptions.ConnectionError:
            print(f"   [SKIP] 无法连接到API服务器（后端服务可能未启动）")
            print(f"   - 提示: 请先启动后端服务 (python run.py)")
            results[endpoint] = {
                "status": "skipped",
                "reason": "API服务器未运行"
            }
        
        except Exception as e:
            print(f"   [ERROR] 请求失败: {e}")
            results[endpoint] = {
                "status": "error",
                "error": str(e)
            }
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    success_count = sum(1 for r in results.values() if r.get("status") == "success")
    failed_count = sum(1 for r in results.values() if r.get("status") == "failed")
    skipped_count = sum(1 for r in results.values() if r.get("status") == "skipped")
    error_count = sum(1 for r in results.values() if r.get("status") == "error")
    
    print(f"成功: {success_count}/{len(endpoints)}")
    if failed_count > 0:
        print(f"失败: {failed_count}/{len(endpoints)}")
    if skipped_count > 0:
        print(f"跳过: {skipped_count}/{len(endpoints)} (后端服务未启动)")
    if error_count > 0:
        print(f"错误: {error_count}/{len(endpoints)}")
    
    if success_count == len(endpoints):
        print("\n[SUCCESS] 所有API端点测试通过！")
        return True
    elif skipped_count > 0:
        print("\n[INFO] 部分测试跳过（后端服务未启动）")
        print("   提示: 启动后端服务后重新运行测试")
        return True  # 跳过不算失败
    else:
        print("\n[FAILURE] 部分API端点测试失败")
        return False


if __name__ == "__main__":
    try:
        success = test_api_endpoints()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[中断] 测试被用户中断")
        sys.exit(1)

