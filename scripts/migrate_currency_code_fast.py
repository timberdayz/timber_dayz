#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速迁移currency_code字段 - 使用autocommit模式
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect, text
from backend.utils.config import get_settings

def migrate():
    """快速迁移"""
    settings = get_settings()
    # 使用autocommit模式
    engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
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
    print("快速迁移 currency_code 字段")
    print("=" * 60)
    
    success = 0
    skipped = 0
    
    with engine.connect() as conn:
        for idx, table in enumerate(tables, 1):
            print(f"\n[{idx}/{len(tables)}] {table}")
            
            if not inspector.has_table(table):
                print("  [SKIP] 表不存在")
                skipped += 1
                continue
            
            # 检查字段
            cols = [c['name'] for c in inspector.get_columns(table)]
            has_field = 'currency_code' in cols
            
            # 检查索引
            idxs = [i['name'] for i in inspector.get_indexes(table)]
            idx_name = f'ix_{table}_currency'
            has_idx = idx_name in idxs
            
            if has_field and has_idx:
                print("  [OK] 已迁移")
                success += 1
                continue
            
            try:
                # 添加字段
                if not has_field:
                    print("  [*] 添加字段...", end=" ", flush=True)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN currency_code VARCHAR(3) NULL"))
                    print("OK", end="")
                
                # 创建索引（异步，不等待）
                if not has_idx:
                    print(" 创建索引...", end=" ", flush=True)
                    conn.execute(text(f"CREATE INDEX {idx_name} ON {table}(currency_code)"))
                    print("OK")
                else:
                    print()
                
                success += 1
                
            except Exception as e:
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    print(f"  [SKIP] {e}")
                    success += 1
                else:
                    print(f"  [ERROR] {e}")
    
    print("\n" + "=" * 60)
    print(f"完成: 成功 {success}, 跳过 {skipped}")
    print("=" * 60)
    
    return success == len(tables) - skipped

if __name__ == "__main__":
    try:
        ok = migrate()
        sys.exit(0 if ok else 1)
    except KeyboardInterrupt:
        print("\n\n[WARN] 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

