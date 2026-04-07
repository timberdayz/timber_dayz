#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查TikTok订单文件结构，确认是否包含订单明细数据
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text
from backend.services.excel_parser import ExcelParser
import pandas as pd

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_tiktok_order_file_structure():
    safe_print("======================================================================")
    safe_print("检查TikTok订单文件结构")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 查找一个已入库的TikTok订单文件
        safe_print("\n[1] 查找已入库的TikTok订单文件...")
        result = db.execute(text("""
            SELECT id, file_name, file_path, status
            FROM catalog_files 
            WHERE platform_code = 'tiktok' 
              AND data_domain = 'orders'
              AND status = 'ingested'
            ORDER BY id DESC 
            LIMIT 1
        """)).fetchone()
        
        if not result:
            safe_print("  未找到已入库的TikTok订单文件")
            return
        
        file_id, file_name, file_path, status = result
        safe_print(f"  文件ID={file_id}, 文件名={file_name}")
        safe_print(f"  文件路径={file_path}")
        
        if not Path(file_path).exists():
            safe_print(f"  [ERROR] 文件不存在: {file_path}")
            return
        
        # 2. 读取文件，检查结构
        safe_print("\n[2] 读取文件结构（使用header_row=1）...")
        try:
            df = ExcelParser.read_excel(file_path, header=1, nrows=10)
            safe_print(f"  文件列数: {len(df.columns)}")
            safe_print(f"  列名: {list(df.columns)[:20]}...")  # 显示前20列
            
            # 检查是否有SKU相关字段
            sku_fields = [col for col in df.columns if 'sku' in str(col).lower() or '商品' in str(col) or '产品' in str(col)]
            safe_print(f"\n  SKU相关字段: {sku_fields}")
            
            # 检查是否有数量相关字段
            qty_fields = [col for col in df.columns if '数量' in str(col) or 'quantity' in str(col).lower() or 'qty' in str(col).lower()]
            safe_print(f"  数量相关字段: {qty_fields}")
            
            # 检查是否有金额相关字段
            amount_fields = [col for col in df.columns if '金额' in str(col) or 'amount' in str(col).lower() or '价格' in str(col) or 'price' in str(col).lower()]
            safe_print(f"  金额相关字段: {amount_fields[:10]}...")  # 显示前10个
            
            # 显示前3行数据示例
            safe_print("\n  前3行数据示例:")
            for idx in range(min(3, len(df))):
                row = df.iloc[idx]
                safe_print(f"\n    第{idx+1}行:")
                # 显示关键字段
                key_fields = ['订单号', '订单ID', 'order_id', '平台SKU', 'platform_sku', '商品SKU', '数量', 'quantity', '金额', 'amount']
                for field in key_fields:
                    matching_cols = [col for col in df.columns if field.lower() in str(col).lower()]
                    for col in matching_cols[:2]:  # 只显示前2个匹配的列
                        value = row[col]
                        if pd.notna(value) and str(value).strip():
                            safe_print(f"      {col}: {value}")
                
        except Exception as e:
            safe_print(f"  读取文件失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 3. 检查fact_orders表中的数据
        safe_print("\n[3] 检查fact_orders表中的数据...")
        order_sample = db.execute(text("""
            SELECT 
                order_id,
                platform_code,
                shop_id,
                total_amount_rmb,
                attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            LIMIT 1
        """)).fetchone()
        
        if order_sample:
            safe_print(f"  示例订单:")
            safe_print(f"    order_id={order_sample[0]}")
            safe_print(f"    platform_code={order_sample[1]}")
            safe_print(f"    shop_id={order_sample[2]}")
            safe_print(f"    total_amount_rmb={order_sample[3]}")
            if order_sample[4]:
                safe_print(f"    attributes中有字段: {list(order_sample[4].keys())[:10] if isinstance(order_sample[4], dict) else 'N/A'}")
        
        safe_print("\n======================================================================")
        safe_print("检查完成")
        safe_print("======================================================================")
        safe_print("\n关键发现:")
        safe_print("  - 如果文件中有SKU、数量、金额等字段，说明包含订单明细数据")
        safe_print("  - 如果只有订单级别字段，说明文件是订单汇总数据")
        safe_print("  - 物化视图需要订单明细数据才能正确计算units_sold和sales_amount")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_tiktok_order_file_structure()

