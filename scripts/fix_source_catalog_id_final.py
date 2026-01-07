#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终修复方案：使用文件创建时间和数据域匹配
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.db import CatalogFile
from sqlalchemy import select
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def fix_by_file_id_final(file_id: int):
    """最终修复方案"""
    safe_print(f"\n[INFO] 修复file_id={file_id}的数据")
    
    db = SessionLocal()
    try:
        # 获取文件信息
        file_record = db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one_or_none()
        
        if not file_record:
            safe_print(f"[ERROR] file_id={file_id}不存在")
            return False
        
        safe_print(f"[INFO] 文件信息: {file_record.file_name}, data_domain={file_record.data_domain}")
        
        # 策略：对于inventory数据，如果StagingInventory的file_id匹配，且FactProductMetric的source_catalog_id为NULL
        # 我们可以通过以下方式匹配：
        # 1. 检查StagingInventory的创建时间范围
        # 2. 查找在同一时间范围内创建的FactProductMetric记录（inventory域）
        # 3. 由于StagingInventory的关键字段都是NULL，我们只能通过时间范围匹配
        
        staging_time = db.execute(text("""
            SELECT 
                MIN(created_at) as min_time,
                MAX(created_at) as max_time,
                COUNT(*) as total
            FROM staging_inventory
            WHERE file_id = :file_id
        """), {"file_id": file_id}).fetchone()
        
        if not staging_time or staging_time[2] == 0:
            safe_print("[WARN] 没有找到StagingInventory记录")
            return False
        
        safe_print(f"\n[INFO] StagingInventory时间范围: {staging_time[0]} ~ {staging_time[1]}")
        safe_print(f"[INFO] StagingInventory记录数: {staging_time[2]}")
        
        # 查找FactProductMetric中inventory数据的时间范围
        fact_time = db.execute(text("""
            SELECT 
                MIN(created_at) as min_time,
                MAX(created_at) as max_time,
                COUNT(*) as total
            FROM fact_product_metrics
            WHERE data_domain = 'inventory' AND source_catalog_id IS NULL
        """)).fetchone()
        
        if not fact_time or fact_time[2] == 0:
            safe_print("[WARN] 没有找到source_catalog_id为NULL的FactProductMetric记录")
            return False
        
        safe_print(f"\n[INFO] FactProductMetric时间范围: {fact_time[0]} ~ {fact_time[1]}")
        safe_print(f"[INFO] FactProductMetric记录数: {fact_time[2]}")
        
        # 如果Fact数据的时间在Staging数据的时间之后，说明是最近同步的
        # 我们可以安全地更新这些数据
        if fact_time[0] >= staging_time[0]:
            # 使用时间范围更新（Fact数据在Staging数据之后创建）
            # 更新所有在Staging时间之后创建的inventory数据
            update_sql = text("""
                UPDATE fact_product_metrics
                SET source_catalog_id = :file_id
                WHERE source_catalog_id IS NULL
                  AND data_domain = 'inventory'
                  AND created_at >= :staging_min_time
            """)
            
            result = db.execute(update_sql, {
                "file_id": file_id,
                "staging_min_time": staging_time[0]
            })
            
            updated_count = result.rowcount
            db.commit()
            
            safe_print(f"\n[OK] 成功修复 {updated_count} 条记录")
            
            # 验证
            verify = db.execute(text("""
                SELECT COUNT(*) 
                FROM fact_product_metrics 
                WHERE source_catalog_id = :file_id AND data_domain = 'inventory'
            """), {"file_id": file_id}).scalar()
            
            safe_print(f"[INFO] 验证: file_id={file_id}的FactProductMetric记录数: {verify}")
            
            return True
        else:
            safe_print("[WARN] Fact数据的时间不在Staging数据的时间范围内，无法安全匹配")
            return False
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 修复失败: {e}", exc_info=True)
        safe_print(f"[ERROR] 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file-id', type=int, required=True)
    args = parser.parse_args()
    
    success = fix_by_file_id_final(args.file_id)
    sys.exit(0 if success else 1)

