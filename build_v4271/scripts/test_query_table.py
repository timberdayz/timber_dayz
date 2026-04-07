#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试查询表数据API
"""

import sys
from pathlib import Path
import requests
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_query_table():
    """测试查询表数据"""
    base_url = "http://localhost:8001/api"
    
    proxies = {'http': None, 'https': None}
    
    print("=" * 70)
    print("测试查询表数据API")
    print("=" * 70)
    
    # 测试查询ab_role表
    table_name = "ab_role"
    
    try:
        response = requests.get(
            f"{base_url}/data-browser/query",
            params={
                "table": table_name,
                "page": 1,
                "page_size": 10
            },
            timeout=30,
            proxies=proxies
        )
        
        print(f"\n状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n响应结构: {list(data.keys())}")
            
            if 'data' in data and 'success' in data:
                if data['success']:
                    result = data['data']
                    print(f"\n数据总数: {result.get('total', 0)}")
                    print(f"数据行数: {len(result.get('data', []))}")
                    print(f"列数 (columns): {len(result.get('columns', []))}")
                    print(f"列数 (columns_detailed): {len(result.get('columns_detailed', []))}")
                    
                    if result.get('columns'):
                        print(f"\ncolumns字段: {result['columns'][:5]}")
                    if result.get('columns_detailed'):
                        print(f"\ncolumns_detailed字段 (前3个):")
                        for col in result['columns_detailed'][:3]:
                            print(f"  {col}")
                else:
                    print(f"\nAPI返回失败: {data.get('message', 'N/A')}")
            else:
                print(f"\n响应格式: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}")
        else:
            print(f"\n错误: {response.text[:500]}")
    except Exception as e:
        print(f"\n异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_query_table()

