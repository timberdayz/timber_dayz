#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查模板中的表头行设置和实际入库情况
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_template_header_row():
    safe_print("======================================================================")
    safe_print("检查模板中的表头行设置")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查tiktok订单模板的表头行设置
        safe_print("\n[1] TikTok订单模板的表头行设置:")
        result = db.execute(text("""
            SELECT id, template_name, platform, data_domain, header_row, created_at
            FROM field_mapping_templates 
            WHERE platform = 'tiktok' AND data_domain = 'orders' 
            ORDER BY id DESC 
            LIMIT 5
        """)).fetchall()
        for r in result:
            safe_print(f"  模板ID={r[0]}, 名称={r[1]}, header_row={r[4]} (0-based), 创建时间={r[5]}")
        
        # 2. 检查最近入库的tiktok订单文件
        safe_print("\n[2] 最近入库的TikTok订单文件:")
        result = db.execute(text("""
            SELECT id, file_name, status, data_domain, last_processed_at
            FROM catalog_files 
            WHERE platform_code = 'tiktok' AND data_domain = 'orders'
            ORDER BY id DESC 
            LIMIT 5
        """)).fetchall()
        for r in result:
            safe_print(f"  文件ID={r[0]}, 文件名={r[1]}, 状态={r[2]}, 处理时间={r[3]}")
        
        # 3. 检查fact_orders表中的最新数据
        safe_print("\n[3] fact_orders表中的最新数据（前5条）:")
        result = db.execute(text("""
            SELECT platform_code, shop_id, order_id, order_date_local, total_amount_rmb, created_at
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            ORDER BY created_at DESC 
            LIMIT 5
        """)).fetchall()
        for r in result:
            safe_print(f"  {r[0]} | {r[1]} | {r[2]} | 日期={r[3]} | 金额={r[4]} | 创建时间={r[5]}")
        
        safe_print("\n======================================================================")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_template_header_row()

