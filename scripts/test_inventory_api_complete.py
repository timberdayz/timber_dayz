#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整测试库存管理API - 验证所有功能
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import json

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_all_apis():
    """测试所有库存管理API"""
    base_url = "http://localhost:8001"
    
    safe_print("\n" + "="*70)
    safe_print("完整测试库存管理API")
    safe_print("="*70)
    
    all_passed = True
    
    # 测试1: 获取库存列表
    safe_print("\n[测试1] 获取库存列表（无筛选）...")
    try:
        response = requests.get(
            f"{base_url}/api/products/products",
            params={"page": 1, "page_size": 20},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                products = data.get("data", [])
                total = data.get("total", 0)
                safe_print(f"  [OK] API调用成功")
                safe_print(f"  总记录数: {total}")
                safe_print(f"  返回记录数: {len(products)}")
                
                if products:
                    safe_print(f"  前3条记录:")
                    for i, p in enumerate(products[:3], 1):
                        safe_print(f"    [{i}] SKU: {p.get('platform_sku')}, 库存: {p.get('stock')}, 价格: {p.get('price')}")
                
                if total == 0:
                    safe_print("  [WARN] 总记录数为0，请检查数据")
                    all_passed = False
            else:
                safe_print(f"  [FAIL] API返回失败: {data.get('message', 'Unknown error')}")
                all_passed = False
        else:
            safe_print(f"  [FAIL] HTTP错误: {response.status_code}")
            safe_print(f"  响应: {response.text[:200]}")
            all_passed = False
    except Exception as e:
        safe_print(f"  [ERROR] 测试失败: {e}")
        all_passed = False
    
    # 测试2: 获取库存统计
    safe_print("\n[测试2] 获取库存统计...")
    try:
        response = requests.get(
            f"{base_url}/api/products/stats/platform-summary",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                stats = data.get("data", {})
                safe_print(f"  [OK] 统计API调用成功")
                safe_print(f"  总产品数: {stats.get('total_products', 0)}")
                safe_print(f"  总库存: {stats.get('total_stock', 0)}")
                safe_print(f"  库存价值: ¥{stats.get('total_value', 0):.2f}")
                safe_print(f"  低库存数量: {stats.get('low_stock_count', 0)}")
                safe_print(f"  缺货数量: {stats.get('out_of_stock_count', 0)}")
                
                platform_breakdown = stats.get('platform_breakdown', [])
                if platform_breakdown:
                    safe_print(f"  平台分布:")
                    for p in platform_breakdown[:5]:
                        safe_print(f"    - {p.get('platform')}: {p.get('product_count')}个产品, {p.get('total_stock')}库存")
            else:
                safe_print(f"  [FAIL] 统计API返回失败: {data.get('message', 'Unknown error')}")
                all_passed = False
        else:
            safe_print(f"  [FAIL] 统计API HTTP错误: {response.status_code}")
            all_passed = False
    except Exception as e:
        safe_print(f"  [ERROR] 统计API测试失败: {e}")
        all_passed = False
    
    # 测试3: 测试筛选功能
    safe_print("\n[测试3] 测试筛选功能（低库存）...")
    try:
        response = requests.get(
            f"{base_url}/api/products/products",
            params={"low_stock": True, "page": 1, "page_size": 10},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                total = data.get("total", 0)
                safe_print(f"  [OK] 低库存筛选成功，找到 {total} 条记录")
            else:
                safe_print(f"  [FAIL] 筛选API返回失败")
                all_passed = False
        else:
            safe_print(f"  [FAIL] 筛选API HTTP错误: {response.status_code}")
            all_passed = False
    except Exception as e:
        safe_print(f"  [ERROR] 筛选API测试失败: {e}")
        all_passed = False
    
    safe_print("\n" + "="*70)
    if all_passed:
        safe_print("[SUCCESS] 所有测试通过！库存管理API正常工作。")
        safe_print("\n建议操作:")
        safe_print("  1. 刷新浏览器页面，查看库存列表")
        safe_print("  2. 检查库存概览看板数据是否正确显示")
        safe_print("  3. 测试筛选和搜索功能")
    else:
        safe_print("[FAIL] 部分测试失败，请检查后端服务和数据库。")
    safe_print("="*70)
    
    return all_passed

if __name__ == "__main__":
    test_all_apis()

