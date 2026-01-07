#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查缺失文件脚本

对比扫描发现的文件数和数据库中注册的文件数，找出缺失的文件。
"""

import sys
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.services.catalog_scanner import scan_and_register
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_missing_files():
    """检查缺失的文件"""
    db = SessionLocal()
    
    try:
        # 1. 统计数据库中的文件数
        db_count = db.query(func.count(CatalogFile.id)).scalar() or 0
        print(f"\n{'='*60}")
        print(f"📊 文件数量对比")
        print(f"{'='*60}")
        print(f"\n数据库中的文件数: {db_count}")
        
        # 2. 执行扫描（不注册，只统计）
        print(f"\n正在扫描文件系统...")
        scan_result = scan_and_register(base_dir="data/raw")
        
        print(f"\n扫描结果:")
        print(f"  - 发现文件数: {scan_result.seen}")
        print(f"  - 新注册文件数: {scan_result.registered}")
        print(f"  - 跳过文件数: {scan_result.skipped}")
        
        # 3. 重新统计数据库中的文件数
        db_count_after = db.query(func.count(CatalogFile.id)).scalar() or 0
        print(f"\n扫描后数据库中的文件数: {db_count_after}")
        
        # 4. 计算差异
        expected_count = scan_result.seen
        actual_count = db_count_after
        diff = expected_count - actual_count
        
        print(f"\n{'='*60}")
        print(f"🔍 差异分析")
        print(f"{'='*60}")
        print(f"\n期望文件数（扫描发现）: {expected_count}")
        print(f"实际文件数（数据库）: {actual_count}")
        print(f"差异: {diff}个文件")
        
        if diff > 0:
            print(f"\n⚠️  有 {diff} 个文件没有被注册到数据库")
            print(f"   可能原因:")
            print(f"   1. 文件格式不支持")
            print(f"   2. 文件是修复缓存文件（data/raw/repaired/**）")
            print(f"   3. 文件元数据解析失败")
            print(f"   4. 文件在注册时发生错误")
            print(f"   5. 文件被跳过（白名单校验失败）")
        elif diff < 0:
            print(f"\n⚠️  数据库中的文件数多于扫描发现的文件数")
            print(f"   可能原因:")
            print(f"   1. 数据库中有历史文件")
            print(f"   2. 文件被移动到其他目录")
        else:
            print(f"\n✅ 文件数量一致")
        
        # 5. 检查各状态的文件数
        print(f"\n{'='*60}")
        print(f"📋 文件状态分布")
        print(f"{'='*60}")
        
        status_counts = {}
        all_statuses = ['pending', 'needs_shop', 'partial_success', 'failed', 'quarantined', 'ingested', 'processing', 'validated', 'skipped']
        
        for status in all_statuses:
            count = db.query(func.count(CatalogFile.id)).filter(
                CatalogFile.status == status
            ).scalar() or 0
            if count > 0:
                status_counts[status] = count
                print(f"  - {status}: {count}个")
        
        # 检查NULL状态
        null_count = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status.is_(None)
        ).scalar() or 0
        if null_count > 0:
            print(f"  - NULL: {null_count}个")
        
        # 检查其他未知状态
        from sqlalchemy import select
        other_statuses = db.execute(
            select(CatalogFile.status, func.count(CatalogFile.id).label('count'))
            .group_by(CatalogFile.status)
        ).all()
        
        known_statuses = set(all_statuses) | {None}
        for status, count in other_statuses:
            if status not in known_statuses:
                print(f"  - {status} (未知状态): {count}个")
        
        print(f"\n{'='*60}\n")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        print(f"\n❌ 检查失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_missing_files()

