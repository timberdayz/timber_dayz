# -*- coding: utf-8 -*-
"""
检查TikTok订单文件的元数据，看是否有shop_id和currency信息
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_file_metadata():
    """检查文件元数据"""
    db = next(get_db())
    try:
        # 检查catalog_files表中的TikTok订单文件
        files = db.execute(text("""
            SELECT 
                id,
                file_name,
                platform_code,
                data_domain,
                shop_id,
                account_id,
                status,
                rows_ingested
            FROM catalog_files 
            WHERE platform_code = 'tiktok' 
              AND data_domain = 'orders'
            ORDER BY created_at DESC
            LIMIT 5
        """)).fetchall()
        
        safe_print("TikTok订单文件元数据:")
        for file_record in files:
            safe_print(f"\n文件ID: {file_record[0]}")
            safe_print(f"  文件名: {file_record[1]}")
            safe_print(f"  平台: {file_record[2]}")
            safe_print(f"  数据域: {file_record[3]}")
            safe_print(f"  shop_id: {file_record[4] or '(NULL)'}")
            safe_print(f"  account_id: {file_record[5] or '(NULL)'}")
            safe_print(f"  状态: {file_record[6]}")
            safe_print(f"  入库行数: {file_record[7]}")
        
        # 检查订单表中的file_id关联
        safe_print("\n检查订单与文件的关联:")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT file_id) as unique_files,
                COUNT(CASE WHEN file_id IS NOT NULL THEN 1 END) as has_file_id
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
        """)).fetchone()
        
        if result:
            total, unique_files, has_file_id = result
            safe_print(f"  总订单数: {total}")
            safe_print(f"  有file_id的订单: {has_file_id}")
            safe_print(f"  唯一文件数: {unique_files}")
        
        # 检查是否有订单关联了file_id
        if result and result[2] > 0:
            sample = db.execute(text("""
                SELECT 
                    fo.order_id,
                    fo.file_id,
                    cf.shop_id as file_shop_id,
                    cf.account_id as file_account_id
                FROM fact_orders fo
                LEFT JOIN catalog_files cf ON fo.file_id = cf.id
                WHERE fo.platform_code = 'tiktok'
                  AND fo.file_id IS NOT NULL
                LIMIT 5
            """)).fetchall()
            
            safe_print("\n订单与文件关联示例:")
            for order_id, file_id, file_shop_id, file_account_id in sample:
                safe_print(f"  订单 {order_id}: file_id={file_id}, file_shop_id={file_shop_id or '(NULL)'}, file_account_id={file_account_id or '(NULL)'}")
    finally:
        db.close()

if __name__ == "__main__":
    check_file_metadata()

