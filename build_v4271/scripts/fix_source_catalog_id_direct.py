#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接使用SQL修复已存在数据的source_catalog_id字段（v4.13.3）

避免ORM字段不匹配问题，直接使用原生SQL
"""

import sys
from pathlib import Path

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

def check_table_structure():
    """检查fact_product_metrics表的实际结构"""
    safe_print("\n[INFO] 检查fact_product_metrics表的实际结构")
    
    db = SessionLocal()
    try:
        # 查询表结构
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'fact_product_metrics'
            ORDER BY ordinal_position
        """))
        
        columns = result.fetchall()
        safe_print("\n[INFO] fact_product_metrics表的字段:")
        for col_name, col_type in columns:
            safe_print(f"  - {col_name}: {col_type}")
        
        # 检查是否有metric_type字段
        has_metric_type = any(col[0] == 'metric_type' for col in columns)
        safe_print(f"\n[INFO] 是否有metric_type字段: {has_metric_type}")
        
        return has_metric_type
        
    finally:
        db.close()

def fix_by_file_id_direct(file_id: int):
    """直接使用SQL更新source_catalog_id"""
    safe_print(f"\n[INFO] 修复file_id={file_id}的数据")
    
    db = SessionLocal()
    try:
        # 策略1: 对于inventory数据，如果StagingInventory的platform_code/shop_id/platform_sku都是NULL
        # 我们可以通过created_at时间戳来匹配（同一文件的数据应该在同一时间入库）
        
        # 首先检查StagingInventory的数据特征
        staging_info = db.execute(text("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(DISTINCT platform_code) as platform_count,
                COUNT(DISTINCT shop_id) as shop_count,
                COUNT(DISTINCT platform_sku) as sku_count,
                MIN(created_at) as min_created,
                MAX(created_at) as max_created
            FROM staging_inventory
            WHERE file_id = :file_id
        """), {"file_id": file_id}).fetchone()
        
        safe_print(f"\n[INFO] StagingInventory统计:")
        safe_print(f"  总记录数: {staging_info[0]}")
        safe_print(f"  不同platform_code数: {staging_info[1]}")
        safe_print(f"  不同shop_id数: {staging_info[2]}")
        safe_print(f"  不同platform_sku数: {staging_info[3]}")
        safe_print(f"  创建时间范围: {staging_info[4]} ~ {staging_info[5]}")
        
        # 策略2: 如果StagingInventory的所有关键字段都是NULL，我们使用时间范围匹配
        # 查找在同一时间范围内创建的FactProductMetric记录（inventory域，source_catalog_id为NULL）
        
        if staging_info[0] > 0:
            # 使用时间范围匹配（同一文件的数据应该在同一时间入库）
            update_sql = text("""
                UPDATE fact_product_metrics
                SET source_catalog_id = :file_id
                WHERE source_catalog_id IS NULL
                  AND data_domain = 'inventory'
                  AND created_at >= :min_time
                  AND created_at <= :max_time
            """)
            
            result = db.execute(update_sql, {
                "file_id": file_id,
                "min_time": staging_info[4],
                "max_time": staging_info[5]
            })
            
            updated_count = result.rowcount
            db.commit()
            
            safe_print(f"\n[OK] 成功修复 {updated_count} 条记录（使用时间范围匹配）")
            
            # 验证修复结果
            verify_result = db.execute(text("""
                SELECT COUNT(*) 
                FROM fact_product_metrics 
                WHERE source_catalog_id = :file_id AND data_domain = 'inventory'
            """), {"file_id": file_id}).scalar()
            
            safe_print(f"[INFO] 验证: file_id={file_id}的FactProductMetric记录数: {verify_result}")
            
            return True
        else:
            safe_print("[WARN] 没有找到StagingInventory记录")
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

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复已存在数据的source_catalog_id字段')
    parser.add_argument('--file-id', type=int, required=True, help='指定file_id，修复该文件的数据')
    parser.add_argument('--check-structure', action='store_true', help='检查表结构')
    
    args = parser.parse_args()
    
    if args.check_structure:
        check_table_structure()
        return 0
    
    success = fix_by_file_id_direct(args.file_id)
    
    if success:
        safe_print("\n[OK] 修复完成！")
        safe_print("[INFO] 请刷新数据流转页面查看结果")
        return 0
    else:
        safe_print("\n[ERROR] 修复失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())

