#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查所有 schema 中的 alembic_version 表"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import engine

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)

safe_print("检查所有 schema 中的 alembic_version 表:\n")

inspector = inspect(engine)
schemas = ['public', 'core', 'a_class', 'b_class', 'c_class']

for schema in schemas:
    try:
        tables = inspector.get_table_names(schema=schema)
        if 'alembic_version' in tables:
            with engine.connect() as conn:
                result = conn.execute(text(f'SELECT version_num FROM "{schema}".alembic_version'))
                version = result.scalar()
                safe_print(f"[{schema}] alembic_version = {version}")
    except Exception as e:
        pass

safe_print("\n检查完成")
