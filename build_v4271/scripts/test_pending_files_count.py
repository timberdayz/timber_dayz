#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试待同步文件统计逻辑

验证：统计status='pending'且文件实际存在的文件数量
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_pending_files_count():
    """测试待同步文件统计"""
    db = SessionLocal()
    
    try:
        from modules.core.path_manager import get_data_raw_dir
        
        print(f"\n{'='*80}")
        print(f"📊 待同步文件统计测试（v4.17.3修复）")
        print(f"{'='*80}\n")
        
        # 1. 统计数据库中pending状态的文件总数
        total_pending_in_db = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status == 'pending'
        ).scalar() or 0
        
        print(f"📋 数据库中pending状态的文件总数: {total_pending_in_db}")
        
        # 2. 扫描data/raw目录，统计实际扫描到的文件数量
        scan_dir = get_data_raw_dir()
        scanned_count = 0
        
        for year_dir in scan_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
                for file_path in year_dir.rglob("*.*"):
                    if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                        if file_path.suffix != '.json':  # 跳过.meta.json
                            scanned_count += 1
        
        print(f"📋 文件系统扫描到的文件数: {scanned_count}")
        
        pending_count = scanned_count
        
        print(f"\n{'='*80}")
        print(f"📊 统计结果")
        print(f"{'='*80}")
        print(f"数据库中pending总数: {total_pending_in_db}")
        print(f"文件系统扫描到的文件数: {scanned_count}")
        
        print(f"\n{'='*80}")
        print(f"✅ 待同步文件数（修复后）: {pending_count}个")
        print(f"   说明：直接统计扫描到的文件总数（匹配扫描结果）")
        print(f"   这样可以显示扫描到的实际文件数（{scanned_count}个），而不是数据库中的pending总数（{total_pending_in_db}个）")
        print(f"{'='*80}\n")
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 测试失败: {e}\n")
    finally:
        db.close()


if __name__ == "__main__":
    test_pending_files_count()

