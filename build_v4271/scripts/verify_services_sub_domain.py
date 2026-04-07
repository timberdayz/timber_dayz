#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证services sub_domain修复结果"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import SessionLocal

db = SessionLocal()
try:
    result1 = db.execute(text("SELECT COUNT(*) FROM catalog_files WHERE data_domain = 'services' AND (sub_domain IS NULL OR sub_domain = '')")).scalar()
    result2 = db.execute(text("SELECT COUNT(*) FROM catalog_files WHERE data_domain = 'services' AND sub_domain = 'agent'")).scalar()
    print(f'剩余sub_domain为空的services文件: {result1}')
    print(f'sub_domain为agent的services文件: {result2}')
finally:
    db.close()

