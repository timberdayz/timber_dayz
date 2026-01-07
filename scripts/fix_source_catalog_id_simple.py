#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单修复已存在数据的source_catalog_id字段（v4.13.3）

使用SQL UPDATE直接更新，避免ORM字段不匹配问题
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal, engine
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def fix_by_file_id(file_id: int):
    """通过file_id修复特定文件的数据"""
    safe_print(f"\n[INFO] 修复file_id={file_id}的数据")
    
    db = SessionLocal()
    try:
        # 使用SQL UPDATE直接更新
        # 策略：通过StagingInventory表关联，更新FactProductMetric表的source_catalog_id
        
        # Step 1: 更新inventory数据（通过StagingInventory关联）
        update_sql_inventory = text("""
            UPDATE fact_product_metrics fpm
            SET source_catalog_id = :file_id
            FROM staging_inventory si
            WHERE fpm.source_catalog_id IS NULL
              AND fpm.data_domain = 'inventory'
              AND fpm.platform_code = si.platform_code
              AND (fpm.shop_id = si.shop_id OR (fpm.shop_id IS NULL AND si.shop_id IS NULL))
              AND (fpm.platform_sku = si.platform_sku OR (fpm.platform_sku IS NULL AND si.platform_sku IS NULL))
              AND si.file_id = :file_id
        """)
        
        result_inventory = db.execute(update_sql_inventory, {"file_id": file_id})
        updated_inventory = result_inventory.rowcount
        
        # Step 2: 更新products/traffic/analytics数据（通过StagingProductMetrics关联）
        update_sql_products = text("""
            UPDATE fact_product_metrics fpm
            SET source_catalog_id = :file_id
            FROM staging_product_metrics spm
            WHERE fpm.source_catalog_id IS NULL
              AND fpm.data_domain IN ('products', 'traffic', 'analytics')
              AND fpm.platform_code = spm.platform_code
              AND fpm.shop_id = spm.shop_id
              AND fpm.platform_sku = spm.platform_sku
              AND spm.file_id = :file_id
        """)
        
        result_products = db.execute(update_sql_products, {"file_id": file_id})
        updated_products = result_products.rowcount
        
        db.commit()
        
        total_updated = updated_inventory + updated_products
        safe_print(f"[OK] 成功修复 {total_updated} 条记录")
        safe_print(f"[INFO]   - inventory数据: {updated_inventory} 条")
        safe_print(f"[INFO]   - products/traffic/analytics数据: {updated_products} 条")
        
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

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复已存在数据的source_catalog_id字段')
    parser.add_argument('--file-id', type=int, required=True, help='指定file_id，修复该文件的数据')
    
    args = parser.parse_args()
    
    success = fix_by_file_id(args.file_id)
    
    if success:
        safe_print("\n[OK] 修复完成！")
        safe_print("[INFO] 请刷新数据流转页面查看结果")
        return 0
    else:
        safe_print("\n[ERROR] 修复失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())

