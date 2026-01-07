#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据浏览器API
检查后端返回的数据结构，特别是schema字段
"""

import sys
from pathlib import Path
import requests
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_get_tables():
    """测试获取表列表API"""
    base_url = "http://localhost:8001/api"
    
    print("=" * 70)
    print("测试数据浏览器API - 获取表列表")
    print("=" * 70)
    
    try:
        # ⭐ 修复：禁用代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.get(f"{base_url}/data-browser/tables", timeout=30, proxies=proxies)
        print(f"\n状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n响应结构: {list(data.keys())}")
            
            if 'data' in data and 'tables' in data['data']:
                tables = data['data']['tables']
                print(f"\n表总数: {len(tables)}")
                
                # 检查前10个表的schema信息
                print("\n前10个表的schema信息:")
                for i, table in enumerate(tables[:10], 1):
                    print(f"  {i}. {table.get('name', 'N/A')}")
                    print(f"     schema: {table.get('schema', 'N/A')}")
                    print(f"     category: {table.get('category', 'N/A')}")
                    print(f"     qualified_name: {table.get('qualified_name', 'N/A')}")
                
                # 统计schema分布
                schema_dist = {}
                for table in tables:
                    schema = table.get('schema') or table.get('category') or 'unknown'
                    schema_dist[schema] = schema_dist.get(schema, 0) + 1
                
                print("\nSchema分布:")
                for schema, count in sorted(schema_dist.items()):
                    print(f"  {schema}: {count}表")
            else:
                print("\n响应格式异常:", json.dumps(data, indent=2, ensure_ascii=False)[:500])
        else:
            print(f"\n错误: {response.text[:500]}")
    except Exception as e:
        print(f"\n异常: {e}")

if __name__ == "__main__":
    test_get_tables()

