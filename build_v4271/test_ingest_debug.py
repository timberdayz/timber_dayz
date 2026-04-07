#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试入库接口详细错误"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.models.database import SessionLocal
from backend.services.data_validator import validate_product_metrics
from backend.services.data_importer import stage_product_metrics, upsert_product_metrics

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

# 测试数据（添加必填字段）
from datetime import date

rows = [
    {
        "platform_code": "shopee",
        "shop_id": "test_shop",
        "product_id": "12345", 
        "platform_sku": "SKU12345",
        "product_name": "测试商品A", 
        "stock": "100",
        "metric_date": date.today(),
        "granularity": "daily"
    },
    {
        "platform_code": "shopee",
        "shop_id": "test_shop",
        "product_id": "12346", 
        "platform_sku": "SKU12346",
        "product_name": "测试商品B", 
        "stock": "200",
        "metric_date": date.today(),
        "granularity": "daily"
    },
]

safe_print("测试数据验证...")
try:
    validation_result = validate_product_metrics(rows)
    safe_print(f"[OK] 验证成功")
    safe_print(f"  错误数: {len(validation_result.get('errors', []))}")
    safe_print(f"  警告数: {len(validation_result.get('warnings', []))}")
except Exception as e:
    safe_print(f"[ERROR] 验证失败: {e}")
    import traceback
    traceback.print_exc()

safe_print("\n测试数据暂存...")
try:
    db = SessionLocal()
    staged = stage_product_metrics(db, rows)
    safe_print(f"[OK] 暂存成功: {staged} 行")
    db.close()
except Exception as e:
    safe_print(f"[ERROR] 暂存失败: {e}")
    import traceback
    traceback.print_exc()

safe_print("\n测试数据upsert...")
try:
    db = SessionLocal()
    imported = upsert_product_metrics(db, rows)
    safe_print(f"[OK] Upsert成功: {imported} 行")
    db.commit()
    db.close()
except Exception as e:
    safe_print(f"[ERROR] Upsert失败: {e}")
    import traceback
    traceback.print_exc()

