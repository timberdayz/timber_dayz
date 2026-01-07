#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断表头行问题：检查入库时是否正确使用了header_row参数
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

def diagnose_header_row_issue():
    safe_print("======================================================================")
    safe_print("诊断表头行问题")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查最近入库的tiktok订单文件及其使用的模板
        safe_print("\n[1] 检查最近入库的TikTok订单文件:")
        result = db.execute(text("""
            SELECT 
                cf.id,
                cf.file_name,
                cf.status,
                cf.last_processed_at,
                cf.error_message
            FROM catalog_files cf
            WHERE cf.platform_code = 'tiktok' 
              AND cf.data_domain = 'orders'
              AND cf.status = 'ingested'
            ORDER BY cf.last_processed_at DESC
            LIMIT 3
        """)).fetchall()
        for r in result:
            safe_print(f"  文件ID={r[0]}, 文件名={r[1]}, 状态={r[2]}, 处理时间={r[3]}")
            if r[4]:
                safe_print(f"    错误信息: {r[4]}")
        
        # 2. 检查这些文件对应的模板
        safe_print("\n[2] 检查对应的模板（tiktok_orders_weekly_v3）:")
        result = db.execute(text("""
            SELECT id, template_name, platform, data_domain, header_row, granularity
            FROM field_mapping_templates 
            WHERE template_name = 'tiktok_orders__weekly_v3'
            LIMIT 1
        """)).fetchone()
        if result:
            safe_print(f"  模板ID={result[0]}, header_row={result[4]} (0-based)")
            safe_print(f"  说明: header_row={result[4]}表示Excel的第{result[4]+1}行是表头")
        
        # 3. 检查fact_orders表中的数据，看看是否有异常
        safe_print("\n[3] 检查fact_orders表中的数据（查看是否有表头行被当作数据）:")
        # 检查是否有order_id看起来像表头（如包含中文或特殊字符）
        result = db.execute(text("""
            SELECT 
                platform_code,
                order_id,
                order_date_local,
                total_amount_rmb,
                attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND (
                order_id ~ '[^0-9]' OR  -- 包含非数字字符
                LENGTH(order_id) > 20 OR  -- 长度异常
                order_id LIKE '%订单%' OR  -- 包含中文"订单"
                order_id LIKE '%Order%' OR  -- 包含英文"Order"
                order_id LIKE '%ID%'  -- 包含"ID"
              )
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()
        if result:
            safe_print("  发现可能的表头行数据（order_id包含非数字字符）:")
            for r in result:
                safe_print(f"    order_id={r[1]}, 日期={r[2]}, 金额={r[3]}")
        else:
            safe_print("  未发现明显的表头行数据（order_id都是数字）")
        
        # 4. 检查是否有order_id为空的记录
        safe_print("\n[4] 检查是否有order_id为空的记录:")
        count = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_orders 
            WHERE platform_code = 'tiktok' 
              AND (order_id IS NULL OR order_id = '')
        """)).scalar()
        safe_print(f"  order_id为空的记录数: {count}")
        
        safe_print("\n======================================================================")
        safe_print("诊断完成")
        safe_print("======================================================================")
        safe_print("\n关键发现:")
        safe_print("  - 模板中header_row=1（0-based），即Excel的第2行是表头")
        safe_print("  - 如果用户设置headerRow=1，这是正确的")
        safe_print("  - 但如果实际Excel的第1行是表头，应该设置headerRow=0")
        safe_print("\n可能的问题:")
        safe_print("  1. 用户误解了0-based的含义（认为'第1行'就是设置1）")
        safe_print("  2. 入库时header_row参数没有正确传递或使用")
        safe_print("  3. 预览和入库使用了不同的header_row值")
        
    except Exception as e:
        safe_print(f"诊断失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    diagnose_header_row_issue()

