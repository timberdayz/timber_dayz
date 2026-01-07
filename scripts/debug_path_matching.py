#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试路径匹配问题

检查数据库中的file_path和扫描到的文件路径格式是否一致

v4.18.0: 使用相对路径比较，与数据库存储格式一致
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
    # 1. 获取扫描目录中的前5个文件路径
    scan_dir = get_data_raw_dir()
    scanned_files = []
    for year_dir in scan_dir.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
            for file_path in year_dir.rglob("*.*"):
                if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                    if file_path.suffix != '.json':
                        scanned_files.append(file_path)
                        if len(scanned_files) >= 5:
                            break
                if len(scanned_files) >= 5:
                    break
    
    print(f"\n扫描到的文件路径（前5个）:")
    for f in scanned_files:
        relative_path = str(f)  # 保持相对路径格式
        print(f"  - {relative_path}")
        print(f"    exists(): {f.exists()}")
        print()
    
    # 2. 获取数据库中的前5个pending文件路径
    pending_files = db.query(CatalogFile.file_path).filter(
        CatalogFile.status == 'pending',
        CatalogFile.source == 'data/raw',
        CatalogFile.file_path.isnot(None)
    ).limit(5).all()
    
    print(f"\n数据库中的文件路径（前5个）:")
    for (db_file_path,) in pending_files:
        print(f"  - {db_file_path}")
        db_path = Path(db_file_path)
        print(f"    exists(): {db_path.exists()}")
        print()
    
    # 3. 检查路径匹配（使用相对路径比较）
    scanned_paths_set = {str(f) for f in scanned_files}
    db_paths_set = {fp for (fp,) in pending_files}
    
    print(f"\n路径匹配测试（使用相对路径）:")
    print(f"扫描到的路径集合（前5个）: {scanned_paths_set}")
    print(f"数据库路径集合（前5个）: {db_paths_set}")
    print(f"交集: {scanned_paths_set & db_paths_set}")
    
finally:
    db.close()

