#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查看mv_inventory_summary的实际字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

db = next(get_db())

result = db.execute(text("""
    SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)
    FROM pg_catalog.pg_attribute a
    JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
    JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
    AND c.relname = 'mv_inventory_summary'
    AND a.attnum > 0
    AND NOT a.attisdropped
    ORDER BY a.attnum
"""))

print("mv_inventory_summary字段列表:")
for row in result.fetchall():
    print(f"  - {row[0]} ({row[1]})")

db.close()

