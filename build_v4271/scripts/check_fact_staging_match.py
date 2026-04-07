#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查Fact表和Staging表的匹配情况
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import FactProductMetric, StagingInventory, CatalogFile
from sqlalchemy import select, func, and_, or_
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_match(file_id: int):
    safe_print(f"\n[INFO] 检查file_id={file_id}的数据匹配情况")
    
    db = SessionLocal()
    try:
        # 检查StagingInventory数据
        staging_records = db.query(StagingInventory).filter(
            StagingInventory.file_id == file_id
        ).limit(5).all()
        
        safe_print(f"\n[INFO] StagingInventory样本数据（前5条）:")
        for i, rec in enumerate(staging_records, 1):
            safe_print(f"  {i}. platform_code={rec.platform_code}, shop_id={rec.shop_id}, platform_sku={rec.platform_sku}")
        
        # 检查FactProductMetric数据（inventory域，source_catalog_id为NULL）
        fact_records = db.query(FactProductMetric).filter(
            and_(
                FactProductMetric.data_domain == 'inventory',
                FactProductMetric.source_catalog_id.is_(None)
            )
        ).limit(5).all()
        
        safe_print(f"\n[INFO] FactProductMetric样本数据（inventory域，source_catalog_id为NULL，前5条）:")
        for i, rec in enumerate(fact_records, 1):
            safe_print(f"  {i}. platform_code={rec.platform_code}, shop_id={rec.shop_id}, platform_sku={rec.platform_sku}, metric_date={rec.metric_date}")
        
        # 检查是否有匹配的记录
        if staging_records and fact_records:
            staging_sample = staging_records[0]
            fact_sample = fact_records[0]
            
            safe_print(f"\n[INFO] 匹配检查:")
            safe_print(f"  Staging: platform_code={staging_sample.platform_code}, shop_id={staging_sample.shop_id}, platform_sku={staging_sample.platform_sku}")
            safe_print(f"  Fact: platform_code={fact_sample.platform_code}, shop_id={fact_sample.shop_id}, platform_sku={fact_sample.platform_sku}")
            
            # 尝试直接匹配
            matched = db.query(FactProductMetric).filter(
                and_(
                    FactProductMetric.data_domain == 'inventory',
                    FactProductMetric.source_catalog_id.is_(None),
                    FactProductMetric.platform_code == staging_sample.platform_code,
                    or_(
                        and_(FactProductMetric.shop_id == staging_sample.shop_id),
                        and_(FactProductMetric.shop_id.is_(None), staging_sample.shop_id.is_(None))
                    ),
                    or_(
                        and_(FactProductMetric.platform_sku == staging_sample.platform_sku),
                        and_(FactProductMetric.platform_sku.is_(None), staging_sample.platform_sku.is_(None))
                    )
                )
            ).count()
            
            safe_print(f"  [INFO] 可以匹配的记录数: {matched}")
        
        # 检查该文件的Fact记录总数
        fact_total = db.query(func.count(FactProductMetric.platform_code)).filter(
            FactProductMetric.source_catalog_id == file_id,
            FactProductMetric.data_domain == 'inventory'
        ).scalar() or 0
        
        safe_print(f"\n[INFO] file_id={file_id}的FactProductMetric记录:")
        safe_print(f"  source_catalog_id={file_id}的记录数: {fact_total}")
        
        fact_null = db.query(func.count(FactProductMetric.platform_code)).filter(
            FactProductMetric.source_catalog_id.is_(None),
            FactProductMetric.data_domain == 'inventory'
        ).scalar() or 0
        
        safe_print(f"  source_catalog_id为NULL的记录数: {fact_null}")
        
    finally:
        db.close()

if __name__ == "__main__":
    check_match(1106)

