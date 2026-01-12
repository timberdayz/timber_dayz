#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查迁移脚本中的索引名冲突

PostgreSQL中索引名是全局唯一的，不能重复。
"""

import re
import sys
from pathlib import Path
from collections import Counter

def check_index_conflicts():
    """检查迁移脚本中的索引名冲突"""
    project_root = Path(__file__).parent.parent
    migration_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    if not migration_file.exists():
        print(f"[ERROR] 迁移文件不存在: {migration_file}")
        return False
    
    content = migration_file.read_text(encoding='utf-8')
    
    # 提取所有索引名和对应的表名
    # 模式: op.create_index('index_name', 'table_name', ...)
    index_pattern = r"op\.create_index\(['\"](\w+)['\"],\s*['\"](\w+)['\"]"
    matches = re.findall(index_pattern, content)
    
    # 统计索引名出现次数
    index_names = [name for name, table in matches]
    index_counter = Counter(index_names)
    
    # 找出重复的索引名
    duplicates = {name: count for name, count in index_counter.items() if count > 1}
    
    if duplicates:
        print(f"[ERROR] 发现 {len(duplicates)} 个重复的索引名:")
        print()
        
        for index_name, count in sorted(duplicates.items()):
            print(f"  索引名: {index_name} (出现 {count} 次)")
            # 找出所有使用这个索引名的表
            tables = [table for name, table in matches if name == index_name]
            for table in tables:
                print(f"    - 表: {table}")
            print()
        
        return False
    else:
        print("[OK] 没有发现重复的索引名")
        return True

if __name__ == "__main__":
    success = check_index_conflicts()
    sys.exit(0 if success else 1)
