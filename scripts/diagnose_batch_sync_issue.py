#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断批量同步问题
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import CatalogFile
from sqlalchemy import select, func, or_, and_

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def diagnose_batch_sync():
    safe_print("======================================================================")
    safe_print("诊断批量同步问题")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查tiktok平台文件状态分布
        safe_print("\n[1] tiktok平台文件状态分布:")
        result = db.execute(select(CatalogFile.status, func.count(CatalogFile.id)).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        ).group_by(CatalogFile.status)).fetchall()
        for r in result:
            safe_print(f"  status={r[0]}, count={r[1]}")
        
        # 2. 检查tiktok平台待入库文件（按数据域和粒度分组）
        safe_print("\n[2] tiktok平台待入库文件（按数据域和粒度分组）:")
        result = db.execute(select(
            CatalogFile.data_domain,
            CatalogFile.granularity,
            func.count(CatalogFile.id)
        ).where(
            CatalogFile.status == 'pending',
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        ).group_by(CatalogFile.data_domain, CatalogFile.granularity)).fetchall()
        if result:
            for r in result:
                safe_print(f"  domain={r[0]}, granularity={r[1]}, count={r[2]}")
        else:
            safe_print("  无待入库文件")
        
        # 3. 检查tiktok/analytics/weekly文件
        safe_print("\n[3] tiktok/analytics/weekly文件状态:")
        result = db.execute(select(
            CatalogFile.status,
            func.count(CatalogFile.id)
        ).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            ),
            CatalogFile.data_domain == 'analytics',
            CatalogFile.granularity == 'weekly'
        ).group_by(CatalogFile.status)).fetchall()
        if result:
            for r in result:
                safe_print(f"  status={r[0]}, count={r[1]}")
        else:
            safe_print("  无符合条件的文件")
        
        # 4. 检查最近处理的tiktok文件
        safe_print("\n[4] 最近处理的tiktok文件（最近10个）:")
        result = db.execute(select(CatalogFile).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        ).order_by(CatalogFile.last_processed_at.desc()).limit(10)).scalars().all()
        for f in result:
            safe_print(f"  {f.file_name}: status={f.status}, domain={f.data_domain}, granularity={f.granularity}, processed_at={f.last_processed_at}")
        
        # 5. 检查所有平台待入库文件
        safe_print("\n[5] 所有平台待入库文件数:")
        result = db.execute(select(func.count(CatalogFile.id)).where(
            CatalogFile.status == 'pending'
        )).scalar()
        safe_print(f"  total={result}")
        
        safe_print("\n======================================================================")
        safe_print("诊断完成")
        safe_print("======================================================================")
        
    except Exception as e:
        safe_print(f"诊断失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    diagnose_batch_sync()

