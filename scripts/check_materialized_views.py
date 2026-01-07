#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查现有物化视图列表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT schemaname, matviewname 
        FROM pg_matviews 
        WHERE schemaname = 'public' 
        ORDER BY matviewname
    """))
    
    print("现有物化视图列表：")
    print("=" * 70)
    for row in result:
        print(f"  {row[0]}.{row[1]}")

