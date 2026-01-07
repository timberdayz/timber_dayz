#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证needs_shop修复结果"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import SessionLocal

db = SessionLocal()
try:
    result1 = db.execute(text("SELECT COUNT(*) FROM catalog_files WHERE status = 'needs_shop' AND data_domain IN ('orders', 'inventory')")).scalar()
    result2 = db.execute(text("SELECT COUNT(*) FROM catalog_files WHERE status = 'pending' AND data_domain IN ('orders', 'inventory')")).scalar()
    print(f'剩余needs_shop状态的订单和库存文件: {result1}')
    print(f'pending状态的订单和库存文件: {result2}')
finally:
    db.close()

