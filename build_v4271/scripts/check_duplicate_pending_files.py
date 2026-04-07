#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查pending文件的重复情况

统计：
1. 数据库中pending状态的文件总数
2. source='data/raw'的pending文件数
3. 是否有重复的file_hash
4. 实际扫描到的文件数（通过文件系统）
"""

import sys
from pathlib import Path
from collections import Counter

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.core.logger import get_logger
from modules.core.path_manager import get_data_raw_dir

logger = get_logger(__name__)


def check_duplicate_pending_files():
    """检查pending文件的重复情况"""
    db = SessionLocal()
    
    try:
        print(f"\n{'='*80}")
        print(f"📊 检查pending文件重复情况")
        print(f"{'='*80}\n")
        
        # 1. 统计数据库中pending状态的文件总数
        total_pending = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status == 'pending'
        ).scalar() or 0
        
        print(f"📋 数据库中pending状态的文件总数: {total_pending}")
        
        # 2. 统计source='data/raw'的pending文件数
        data_raw_pending = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status == 'pending',
            CatalogFile.source == 'data/raw'
        ).scalar() or 0
        
        print(f"📋 source='data/raw'的pending文件数: {data_raw_pending}")
        
        # 3. 检查是否有重复的file_hash
        pending_files = db.query(CatalogFile.file_hash, CatalogFile.file_path).filter(
            CatalogFile.status == 'pending',
            CatalogFile.source == 'data/raw',
            CatalogFile.file_hash.isnot(None)
        ).all()
        
        hash_counts = Counter(hash_val for hash_val, _ in pending_files if hash_val)
        duplicate_hashes = {h: c for h, c in hash_counts.items() if c > 1}
        
        print(f"\n📊 file_hash重复情况:")
        print(f"   唯一hash数: {len(hash_counts)}")
        print(f"   重复hash数: {len(duplicate_hashes)}")
        if duplicate_hashes:
            print(f"   重复hash详情（前10个）:")
            for hash_val, count in list(duplicate_hashes.items())[:10]:
                print(f"     - {hash_val[:16]}... : {count}个文件")
        
        # 4. 统计实际扫描到的文件数（通过文件系统）
        scan_dir = get_data_raw_dir()
        scanned_files = []
        for year_dir in scan_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
                for file_path in year_dir.rglob("*.*"):
                    if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                        if file_path.suffix != '.json':  # 跳过.meta.json
                            scanned_files.append(file_path)
        
        print(f"\n📊 文件系统扫描结果:")
        print(f"   扫描到的文件数: {len(scanned_files)}")
        
        # 5. 统计实际存在的pending文件数
        existing_count = sum(1 for _, file_path in pending_files if file_path and Path(file_path).exists())
        
        print(f"\n{'='*80}")
        print(f"📊 总结")
        print(f"{'='*80}")
        print(f"数据库中pending总数: {total_pending}")
        print(f"source='data/raw'的pending数: {data_raw_pending}")
        print(f"实际存在的pending文件数: {existing_count}")
        print(f"文件系统扫描到的文件数: {len(scanned_files)}")
        print(f"重复hash数: {len(duplicate_hashes)}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        print(f"\n❌ 检查失败: {e}\n")
    finally:
        db.close()


if __name__ == "__main__":
    check_duplicate_pending_files()

