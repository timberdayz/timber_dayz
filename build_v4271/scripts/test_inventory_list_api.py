#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试库存管理API - 验证库存列表是否可以正常显示
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

def test_inventory_list_api():
    """测试库存列表API"""
    base_url = "http://localhost:8001"
    
    safe_print("\n" + "="*70)
    safe_print("测试库存管理API - 库存列表")
    safe_print("="*70)
    
    # 测试1: 获取库存列表（无筛选）
    safe_print("\n[测试1] 获取库存列表（无筛选）...")
    try:
        response = requests.get(
            f"{base_url}/api/products/products",
            params={
                "page": 1,
                "page_size": 20
            },
            timeout=10
        )
        
        safe_print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                products = data.get("data", [])
                total = data.get("total", 0)
                safe_print(f"[OK] API调用成功")
                safe_print(f"  总记录数: {total}")
                safe_print(f"  返回记录数: {len(products)}")
                
                if products:
                    safe_print(f"\n  前3条记录示例:")
                    for i, p in enumerate(products[:3], 1):
                        safe_print(f"    [{i}] SKU: {p.get('platform_sku')}, 名称: {p.get('product_name')}, 库存: {p.get('stock')}")
                
                return True
            else:
                safe_print(f"[FAIL] API返回失败: {data.get('message', 'Unknown error')}")
                return False
        else:
            safe_print(f"[FAIL] HTTP错误: {response.status_code}")
            safe_print(f"  响应内容: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError:
        safe_print("[ERROR] 无法连接到后端服务（请确保后端服务正在运行）")
        return False
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
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
                safe_print(f"[OK] 统计API调用成功")
                safe_print(f"  总产品数: {stats.get('total_products', 0)}")
                safe_print(f"  总库存: {stats.get('total_stock', 0)}")
                safe_print(f"  库存价值: ¥{stats.get('total_value', 0):.2f}")
                safe_print(f"  低库存数量: {stats.get('low_stock_count', 0)}")
                safe_print(f"  缺货数量: {stats.get('out_of_stock_count', 0)}")
                return True
            else:
                safe_print(f"[FAIL] 统计API返回失败: {data.get('message', 'Unknown error')}")
                return False
        else:
            safe_print(f"[FAIL] 统计API HTTP错误: {response.status_code}")
            return False
            
    except Exception as e:
        safe_print(f"[ERROR] 统计API测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_inventory_list_api()
    
    safe_print("\n" + "="*70)
    if success:
        safe_print("[SUCCESS] 所有测试通过！库存列表API正常工作。")
    else:
        safe_print("[FAIL] 测试失败，请检查后端服务和数据库。")
    safe_print("="*70)

