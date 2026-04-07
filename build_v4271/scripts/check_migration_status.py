#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查迁移状态 - 快速检查哪些表已有currency_code字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect
from backend.utils.config import get_settings

def check_status():
    """检查迁移状态"""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    tables = [
        'fact_raw_data_orders_daily',
        'fact_raw_data_orders_weekly',
        'fact_raw_data_orders_monthly',
        'fact_raw_data_products_daily',
        'fact_raw_data_products_weekly',
        'fact_raw_data_products_monthly',
        'fact_raw_data_traffic_daily',
        'fact_raw_data_traffic_weekly',
        'fact_raw_data_traffic_monthly',
        'fact_raw_data_services_daily',
        'fact_raw_data_services_weekly',
        'fact_raw_data_services_monthly',
        'fact_raw_data_inventory_snapshot',
    ]
    
    print("=" * 60)
    print("迁移状态检查")
    print("=" * 60)
    
    migrated = []
    not_migrated = []
    not_exist = []
    
    for table_name in tables:
        if not inspector.has_table(table_name):
            not_exist.append(table_name)
            continue
        
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
        
        has_field = 'currency_code' in columns
        has_index = any('currency' in idx.lower() for idx in indexes)
        
        if has_field and has_index:
            migrated.append(table_name)
            print(f"[OK] {table_name}")
        else:
            not_migrated.append(table_name)
            status = []
            if not has_field:
                status.append("缺少字段")
            if not has_index:
                status.append("缺少索引")
            print(f"[PENDING] {table_name} - {', '.join(status)}")
    
    print("\n" + "=" * 60)
    print(f"统计: 已完成 {len(migrated)}/{len(tables)}, 待迁移 {len(not_migrated)}, 不存在 {len(not_exist)}")
    print("=" * 60)
    
    return len(not_migrated) == 0

if __name__ == "__main__":
    sys.exit(0 if check_status() else 1)
