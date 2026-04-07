#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断数据同步和物化视图问题
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import CatalogFile, FactOrder, FactProductMetric
from sqlalchemy import select, func, or_, and_, text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def diagnose_issues():
    safe_print("======================================================================")
    safe_print("诊断数据同步和物化视图问题")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 问题1: 检查跳过的文件状态
        safe_print("\n[问题1] tiktok平台文件状态分布:")
        result = db.execute(select(CatalogFile.status, func.count(CatalogFile.id)).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        ).group_by(CatalogFile.status)).fetchall()
        for r in result:
            safe_print(f"  status={r[0]}, count={r[1]}")
        
        # 检查跳过的文件详情
        safe_print("\n[问题1] 跳过的文件详情（前10个）:")
        skipped_files = db.execute(select(CatalogFile).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            ),
            CatalogFile.status == 'skipped'
        ).limit(10)).scalars().all()
        for f in skipped_files:
            safe_print(f"  {f.file_name}: status={f.status}, error={f.error_message[:50] if f.error_message else None}")
        
        # 问题2: 检查待入库文件统计
        safe_print("\n[问题2] 待入库文件统计:")
        pending_count = db.execute(select(func.count(CatalogFile.id)).where(
            CatalogFile.status == 'pending',
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        )).scalar()
        safe_print(f"  pending状态文件数: {pending_count}")
        
        # 检查是否有其他状态的文件（可能是跳过的）
        skipped_count = db.execute(select(func.count(CatalogFile.id)).where(
            CatalogFile.status == 'skipped',
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        )).scalar()
        safe_print(f"  skipped状态文件数: {skipped_count}")
        
        # 问题3: 检查订单数据是否入库
        safe_print("\n[问题3] tiktok平台订单数据检查:")
        try:
            order_count = db.execute(text("SELECT COUNT(*) FROM fact_orders WHERE LOWER(platform_code) = 'tiktok'")).scalar()
            safe_print(f"  fact_orders表中tiktok订单数: {order_count}")
        except Exception as e:
            safe_print(f"  查询fact_orders失败: {e}")
        
        # 检查物化视图中的数据
        safe_print("\n[问题3] 物化视图数据检查:")
        try:
            mv_count = db.execute(text("SELECT COUNT(*) FROM mv_product_sales_trend WHERE platform_code = 'tiktok'")).scalar()
            safe_print(f"  mv_product_sales_trend中tiktok数据数: {mv_count}")
        except Exception as e:
            safe_print(f"  查询物化视图失败: {e}")
        
        # 检查fact_product_metrics中的数据
        safe_print("\n[问题3] fact_product_metrics表数据检查:")
        product_metrics_count = db.execute(select(func.count(FactProductMetric.id)).where(
            func.lower(FactProductMetric.platform_code) == 'tiktok',
            FactProductMetric.data_domain == 'products'
        )).scalar()
        safe_print(f"  fact_product_metrics表中tiktok products域数据数: {product_metrics_count}")
        
        # 检查订单数据域
        safe_print("\n[问题3] 检查订单数据域:")
        order_domain_files = db.execute(select(func.count(CatalogFile.id)).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            ),
            CatalogFile.data_domain == 'orders'
        )).scalar()
        safe_print(f"  tiktok平台orders域文件数: {order_domain_files}")
        
        ingested_order_files = db.execute(select(func.count(CatalogFile.id)).where(
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            ),
            CatalogFile.data_domain == 'orders',
            CatalogFile.status == 'ingested'
        )).scalar()
        safe_print(f"  tiktok平台orders域已入库文件数: {ingested_order_files}")
        
        # 检查pending文件的详细信息
        safe_print("\n[问题2] pending文件详细信息（前10个）:")
        pending_files = db.execute(select(CatalogFile).where(
            CatalogFile.status == 'pending',
            or_(
                func.lower(CatalogFile.platform_code) == 'tiktok',
                func.lower(CatalogFile.source_platform) == 'tiktok'
            )
        ).limit(10)).scalars().all()
        for f in pending_files:
            safe_print(f"  {f.file_name}: domain={f.data_domain}, granularity={f.granularity}, first_seen={f.first_seen_at}")
        
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
    diagnose_issues()

