#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试入库接口"""

import requests
import json
import traceback

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

# 简化的测试数据
file_id = 710
platform = "shopee"
domain = "products"

mappings = {
    "商品编号": "product_id",
    "商品": "product_name",
    "库存": "stock"
}

rows = [
    {"商品编号": "12345", "商品": "测试商品A", "库存": "100"},
    {"商品编号": "12346", "商品": "测试商品B", "库存": "200"},
]

payload = {
    "file_id": file_id,
    "platform": platform,
    "domain": domain,
    "mappings": mappings,
    "rows": rows
}

safe_print("测试入库接口")
safe_print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

try:
    response = requests.post(
        "http://localhost:8001/api/field-mapping/ingest",
        json=payload,
        timeout=60
    )
    
    safe_print(f"\n状态码: {response.status_code}")
    safe_print(f"响应: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        safe_print(f"\n[OK] 入库成功!")
        safe_print(json.dumps(result, indent=2, ensure_ascii=False))
    
except Exception as e:
    safe_print(f"[ERROR] {e}")
    traceback.print_exc()

