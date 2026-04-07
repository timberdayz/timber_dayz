#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查扫描到的文件中pending状态的数量

统计：
1. 扫描到的文件总数
2. 扫描到的文件中，status='pending'的数量

v4.18.0: 使用相对路径比较，与数据库存储格式一致，支持云端迁移
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.core.path_manager import get_data_raw_dir

db = SessionLocal()

try:
    # 1. 扫描data/raw目录，获取实际存在的文件路径集合
    scan_dir = get_data_raw_dir()
    scanned_file_paths = {}
    
    for year_dir in scan_dir.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
            for file_path in year_dir.rglob("*.*"):
                if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                    if file_path.suffix != '.json':
                        # v4.18.0: 使用相对路径，与数据库存储格式一致
                        relative_path = str(file_path)
                        scanned_file_paths[relative_path] = file_path
    
    print(f"\n扫描到的文件总数: {len(scanned_file_paths)}")
    
    # 2. 查询数据库中这些文件的状态
    all_files = db.query(CatalogFile.file_path, CatalogFile.status).filter(
        CatalogFile.file_path.isnot(None)
    ).all()
    
    # 构建路径到状态的映射（直接使用数据库中的路径格式）
    path_to_status = {}
    for db_file_path, status in all_files:
        if db_file_path:
            # v4.18.0: 直接使用数据库中存储的路径格式
            path_to_status[db_file_path] = status
    
    # 3. 统计扫描到的文件中，status='pending'的数量
    pending_count = 0
    status_counts = {}
    
    for relative_path in scanned_file_paths:
        status = path_to_status.get(relative_path, 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == 'pending':
            pending_count += 1
    
    print(f"\n扫描到的文件中各状态的数量:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}个")
    
    print(f"\n✅ 扫描到的文件中，status='pending'的数量: {pending_count}个")
    
finally:
    db.close()

