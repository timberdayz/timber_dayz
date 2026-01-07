#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查表结构
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

db = next(get_db())
try:
    # 检查fact_product_metrics表
    cols = db.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'fact_product_metrics' 
        ORDER BY ordinal_position
    """)).fetchall()
    
    safe_print("fact_product_metrics表字段:")
    for col in cols:
        safe_print(f"  - {col[0]:30} ({col[1]})")
        
finally:
    db.close()

