#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查sales_targets表结构"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    result = db.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'sales_targets' 
        ORDER BY ordinal_position
    """))
    cols = result.fetchall()
    print("sales_targets表字段:")
    for col_name, col_type in cols:
        print(f"  - {col_name}: {col_type}")
finally:
    db.close()

