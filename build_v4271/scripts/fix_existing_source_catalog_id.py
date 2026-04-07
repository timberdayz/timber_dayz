#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复已存在数据的source_catalog_id字段（v4.13.3）

功能：
- 更新FactProductMetric表中source_catalog_id为NULL的记录
- 通过Staging表关联file_id，更新Fact表的source_catalog_id
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import FactProductMetric, StagingProductMetrics, StagingInventory, CatalogFile
from sqlalchemy import select, update, and_
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def fix_source_catalog_id():
    """修复已存在数据的source_catalog_id字段"""
    safe_print("\n" + "=" * 60)
    safe_print("修复已存在数据的source_catalog_id字段")
    safe_print("=" * 60)
    
    db = SessionLocal()
    try:
        # Step 1: 查找所有source_catalog_id为NULL的FactProductMetric记录
        null_records = db.query(FactProductMetric).filter(
            FactProductMetric.source_catalog_id.is_(None)
        ).all()
        
        safe_print(f"\n[INFO] 找到 {len(null_records)} 条source_catalog_id为NULL的记录")
        
        if len(null_records) == 0:
            safe_print("[OK] 没有需要修复的记录")
            return True
        
        # Step 2: 通过Staging表关联file_id
        # 策略：对于inventory数据，通过StagingInventory表关联
        # 对于products/traffic/analytics数据，通过StagingProductMetrics表关联
        
        fixed_count = 0
        skipped_count = 0
        
        for fact_record in null_records:
            file_id = None
            
            # 尝试通过StagingProductMetrics关联
            if fact_record.data_domain in ["products", "traffic", "analytics"]:
                staging_record = db.query(StagingProductMetrics).filter(
                    and_(
                        StagingProductMetrics.platform_code == fact_record.platform_code,
                        StagingProductMetrics.shop_id == fact_record.shop_id,
                        StagingProductMetrics.platform_sku == fact_record.platform_sku
                    )
                ).first()
                
                if staging_record and staging_record.file_id:
                    file_id = staging_record.file_id
            
            # 尝试通过StagingInventory关联（inventory数据）
            elif fact_record.data_domain == "inventory":
                # inventory数据可能没有platform_code和shop_id，需要通过其他方式关联
                # 由于inventory数据可能没有唯一标识，我们尝试通过最近的文件关联
                # 这里使用一个简化的策略：查找最近入库的inventory文件
                if fact_record.platform_code:
                    staging_record = db.query(StagingInventory).filter(
                        and_(
                            StagingInventory.platform_code == fact_record.platform_code,
                            StagingInventory.shop_id == fact_record.shop_id,
                            StagingInventory.platform_sku == fact_record.platform_sku
                        )
                    ).first()
                    
                    if staging_record and staging_record.file_id:
                        file_id = staging_record.file_id
            
            # 如果找到了file_id，更新记录
            if file_id:
                # 验证file_id是否存在
                file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
                if file_record:
                    fact_record.source_catalog_id = file_id
                    fixed_count += 1
                else:
                    skipped_count += 1
                    safe_print(f"[WARN] file_id={file_id}不存在，跳过记录")
            else:
                skipped_count += 1
        
        # Step 3: 提交更新
        if fixed_count > 0:
            db.commit()
            safe_print(f"\n[OK] 成功修复 {fixed_count} 条记录")
            safe_print(f"[INFO] 跳过 {skipped_count} 条记录（无法关联file_id）")
        else:
            safe_print(f"\n[WARN] 没有记录被修复")
            safe_print(f"[INFO] 跳过 {skipped_count} 条记录（无法关联file_id）")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 修复失败: {e}", exc_info=True)
        safe_print(f"[ERROR] 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def fix_by_file_id(file_id: int):
    """通过file_id修复特定文件的数据"""
    safe_print(f"\n[INFO] 修复file_id={file_id}的数据")
    
    db = SessionLocal()
    try:
        # 查找该文件的所有Staging记录
        staging_inventory_records = db.query(StagingInventory).filter(
            StagingInventory.file_id == file_id
        ).all()
        
        staging_product_records = db.query(StagingProductMetrics).filter(
            StagingProductMetrics.file_id == file_id
        ).all()
        
        safe_print(f"[INFO] 找到 {len(staging_inventory_records)} 条StagingInventory记录")
        safe_print(f"[INFO] 找到 {len(staging_product_records)} 条StagingProductMetrics记录")
        
        fixed_count = 0
        
        # 更新FactProductMetric表中对应的记录
        for staging_record in staging_inventory_records + staging_product_records:
            # 查找对应的Fact记录
            fact_records = db.query(FactProductMetric).filter(
                and_(
                    FactProductMetric.platform_code == staging_record.platform_code,
                    FactProductMetric.shop_id == staging_record.shop_id,
                    FactProductMetric.platform_sku == staging_record.platform_sku,
                    FactProductMetric.source_catalog_id.is_(None)
                )
            ).all()
            
            for fact_record in fact_records:
                fact_record.source_catalog_id = file_id
                fixed_count += 1
        
        if fixed_count > 0:
            db.commit()
            safe_print(f"[OK] 成功修复 {fixed_count} 条记录")
        else:
            safe_print(f"[INFO] 没有需要修复的记录")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 修复失败: {e}", exc_info=True)
        safe_print(f"[ERROR] 修复失败: {e}")
        return False
    finally:
        db.close()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复已存在数据的source_catalog_id字段')
    parser.add_argument('--file-id', type=int, help='指定file_id，只修复该文件的数据')
    
    args = parser.parse_args()
    
    if args.file_id:
        success = fix_by_file_id(args.file_id)
    else:
        success = fix_source_catalog_id()
    
    if success:
        safe_print("\n[OK] 修复完成！")
        return 0
    else:
        safe_print("\n[ERROR] 修复失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())

