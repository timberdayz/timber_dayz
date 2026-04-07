#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查staging表结构"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # 检查staging_product_metrics表
    cols = db.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'staging_product_metrics'
        ORDER BY ordinal_position
    """)).fetchall()
    
    print("staging_product_metrics表结构:")
    for col_name, col_type in cols:
        print(f"  {col_name}: {col_type}")
    
    has_metric_data = any(c[0] == 'metric_data' for c in cols)
    print(f"\n是否有metric_data字段: {has_metric_data}")
    
finally:
    db.close()

