#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证 config 文件过滤是否正常工作
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import ComponentVersion
from sqlalchemy import not_

db = SessionLocal()
try:
    # 检查是否还有 config 组件
    config_count = db.query(ComponentVersion).filter(
        (ComponentVersion.file_path.like('%_config.py'))
        | (ComponentVersion.file_path.like('%overlay_guard.py'))
        | (ComponentVersion.component_name.like('%_config'))
        | (ComponentVersion.component_name.like('%overlay_guard'))
    ).count()
    
    print(f'[CHECK] 数据库中剩余的 config 组件数量: {config_count}')
    
    # 检查过滤后的查询
    total_count = db.query(ComponentVersion).count()
    
    filtered_query = db.query(ComponentVersion).filter(
        not_(ComponentVersion.file_path.like('%_config.py')),
        not_(ComponentVersion.file_path.like('%overlay_guard.py')),
        not_(ComponentVersion.component_name.like('%_config')),
        not_(ComponentVersion.component_name.like('%overlay_guard'))
    )
    filtered_count = filtered_query.count()
    
    print(f'[CHECK] 数据库总组件数: {total_count}')
    print(f'[CHECK] 过滤后组件数: {filtered_count}')
    
    if config_count == 0 and filtered_count == total_count:
        print('[OK] 过滤逻辑正常工作!')
        sys.exit(0)
    else:
        print(f'[WARN] 仍有 {total_count - filtered_count} 个组件被过滤')
        sys.exit(1)
    
finally:
    db.close()

