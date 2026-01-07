#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证迁移结果"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import engine

with engine.connect() as conn:
    schemas = ['core', 'a_class', 'c_class', 'finance']
    print('Schema表统计:')
    print('=' * 60)
    total = 0
    for s in schemas:
        count = conn.execute(text(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{s}' AND table_type = 'BASE TABLE'")).scalar()
        print(f'{s}: {count} 张表')
        total += count
    print('=' * 60)
    print(f'总计: {total} 张表')

