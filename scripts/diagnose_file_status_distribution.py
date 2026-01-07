#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断文件状态分布脚本

用于检查catalog_files表中各状态的文件数量，帮助诊断统计不一致的问题。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def diagnose_file_status_distribution():
    """诊断文件状态分布"""
    db = SessionLocal()
    
    try:
        # 1. 统计所有文件总数
        total_count = db.query(func.count(CatalogFile.id)).scalar() or 0
        print(f"\n{'='*60}")
        print(f"📊 文件状态分布诊断")
        print(f"{'='*60}")
        print(f"\n总文件数: {total_count}")
        
        # 2. 统计各状态的文件数量
        print(f"\n{'状态':<20} {'数量':<10} {'占比':<10}")
        print(f"{'-'*40}")
        
        all_statuses = [
            'pending',
            'needs_shop',
            'partial_success',
            'failed',
            'quarantined',
            'ingested',
            'processing',
            'validated',
            'skipped'
        ]
        
        status_counts = {}
        for status in all_statuses:
            count = db.query(func.count(CatalogFile.id)).filter(
                CatalogFile.status == status
            ).scalar() or 0
            if count > 0:
                status_counts[status] = count
                percentage = (count / total_count * 100) if total_count > 0 else 0
                print(f"{status:<20} {count:<10} {percentage:.2f}%")
        
        # 3. 统计NULL或未知状态
        null_count = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status.is_(None)
        ).scalar() or 0
        if null_count > 0:
            status_counts['NULL'] = null_count
            percentage = (null_count / total_count * 100) if total_count > 0 else 0
            print(f"{'NULL':<20} {null_count:<10} {percentage:.2f}%")
        
        # 4. 统计其他未知状态
        known_statuses = set(all_statuses) | {None}
        other_statuses_query = db.query(
            CatalogFile.status,
            func.count(CatalogFile.id).label('count')
        ).group_by(CatalogFile.status).all()
        
        other_statuses = []
        for status, count in other_statuses_query:
            if status not in known_statuses:
                other_statuses.append((status, count))
                status_counts[f'unknown_{status}'] = count
                percentage = (count / total_count * 100) if total_count > 0 else 0
                print(f"{f'unknown_{status}':<20} {count:<10} {percentage:.2f}%")
        
        # 5. 计算待同步文件总数（按修复后的逻辑）
        pending_statuses = ['pending', 'partial_success', 'failed', 'quarantined', 'needs_shop']
        pending_count = db.query(func.count(CatalogFile.id)).filter(
            CatalogFile.status.in_(pending_statuses)
        ).scalar() or 0
        
        print(f"\n{'='*60}")
        print(f"📋 待同步文件统计（修复后）")
        print(f"{'='*60}")
        print(f"\n待同步状态列表: {', '.join(pending_statuses)}")
        print(f"待同步文件总数: {pending_count}")
        
        # 6. 详细分解
        print(f"\n详细分解:")
        for status in pending_statuses:
            count = status_counts.get(status, 0)
            if count > 0:
                print(f"  - {status}: {count}个")
        
        # 7. 对比分析
        print(f"\n{'='*60}")
        print(f"🔍 对比分析")
        print(f"{'='*60}")
        print(f"\n总文件数: {total_count}")
        print(f"待同步文件数（修复后）: {pending_count}")
        print(f"已同步文件数: {status_counts.get('ingested', 0)}")
        print(f"其他状态文件数: {total_count - pending_count - status_counts.get('ingested', 0)}")
        
        # 8. 如果差异较大，给出建议
        if total_count > pending_count + status_counts.get('ingested', 0):
            diff = total_count - pending_count - status_counts.get('ingested', 0)
            print(f"\n⚠️  发现差异: {diff}个文件处于其他状态")
            print(f"   建议检查这些状态的文件是否需要同步")
        
        print(f"\n{'='*60}\n")
        
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)
        print(f"\n❌ 诊断失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    diagnose_file_status_distribution()

