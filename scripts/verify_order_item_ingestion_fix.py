#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证订单明细入库逻辑修复 - 测试从attributes中提取字段
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

def verify_order_item_ingestion_fix():
    safe_print("======================================================================")
    safe_print("验证订单明细入库逻辑修复")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查fact_order_items表是否有数据
        safe_print("\n[1] 检查fact_order_items表数据...")
        count = db.execute(text("SELECT COUNT(*) FROM fact_order_items")).scalar()
        safe_print(f"  fact_order_items表记录数: {count}")
        
        if count > 0:
            # 显示示例数据
            sample = db.execute(text("""
                SELECT platform_code, shop_id, order_id, platform_sku, quantity, line_amount_rmb
                FROM fact_order_items
                WHERE platform_code = 'tiktok'
                LIMIT 5
            """)).fetchall()
            
            safe_print(f"\n  TikTok订单明细示例（前5条）:")
            for row in sample:
                safe_print(f"    order_id={row[2]}, platform_sku={row[3]}, quantity={row[4]}, line_amount_rmb={row[5]}")
        
        # 2. 检查fact_orders表的attributes字段，确认是否有订单明细字段
        safe_print("\n[2] 检查fact_orders表的attributes字段...")
        sample_order = db.execute(text("""
            SELECT order_id, attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
        """)).fetchone()
        
        if sample_order and sample_order[1]:
            attrs = sample_order[1]
            safe_print(f"  示例订单 order_id={sample_order[0]}")
            safe_print(f"  attributes中的订单明细相关字段:")
            
            sku_keys = [k for k in attrs.keys() if 'sku' in str(k).lower() or '商品' in str(k) or '产品' in str(k)] if isinstance(attrs, dict) else []
            qty_keys = [k for k in attrs.keys() if '数量' in str(k) or 'quantity' in str(k).lower() or 'qty' in str(k).lower()] if isinstance(attrs, dict) else []
            amount_keys = [k for k in attrs.keys() if '金额' in str(k) or 'amount' in str(k).lower() or '价格' in str(k)] if isinstance(attrs, dict) else []
            
            safe_print(f"    SKU相关: {sku_keys[:10]}")
            safe_print(f"    数量相关: {qty_keys[:10]}")
            safe_print(f"    金额相关: {amount_keys[:10]}")
            
            # 显示具体值
            if sku_keys:
                safe_print(f"\n    SKU字段值示例:")
                for k in sku_keys[:3]:
                    safe_print(f"      {k} = {attrs.get(k)}")
        
        # 3. 检查mv_sales_day_shop_sku物化视图
        safe_print("\n[3] 检查mv_sales_day_shop_sku物化视图...")
        mv_count = db.execute(text("SELECT COUNT(*) FROM mv_sales_day_shop_sku WHERE platform_code = 'tiktok'")).scalar()
        safe_print(f"  TikTok订单物化视图记录数: {mv_count}")
        
        if mv_count > 0:
            # 检查是否有非零的销售金额
            non_zero_count = db.execute(text("""
                SELECT COUNT(*) 
                FROM mv_sales_day_shop_sku 
                WHERE platform_code = 'tiktok' 
                  AND (units_sold > 0 OR sales_amount_cny > 0 OR sales_amount > 0)
            """)).scalar()
            safe_print(f"  非零销售记录数: {non_zero_count}")
            
            if non_zero_count > 0:
                # 显示示例
                sample = db.execute(text("""
                    SELECT platform_code, shop_id, platform_sku, sale_date, 
                           order_count, units_sold, sales_amount_cny, sales_amount, avg_unit_price_cny
                    FROM mv_sales_day_shop_sku
                    WHERE platform_code = 'tiktok'
                      AND (units_sold > 0 OR sales_amount_cny > 0)
                    LIMIT 3
                """)).fetchall()
                
                safe_print(f"\n  非零销售记录示例:")
                for row in sample:
                    safe_print(f"    SKU={row[2]}, 日期={row[3]}, 订单数={row[4]}, 销量={row[5]}, 销售额(CNY)={row[6]}, 销售额={row[7]}, 均价={row[8]}")
            else:
                safe_print("  ⚠️ 警告：所有记录的销售金额都为0，订单明细可能未正确入库")
        
        safe_print("\n======================================================================")
        safe_print("验证完成")
        safe_print("======================================================================")
        safe_print("\n修复说明:")
        safe_print("  1. 订单明细入库逻辑已更新，能够从attributes JSON中提取字段")
        safe_print("  2. 支持多种字段名（标准字段名、中文字段名、大小写变体）")
        safe_print("  3. 如果fact_order_items表仍为空，请重新入库订单数据")
        safe_print("  4. 重新入库后，运行此脚本验证订单明细是否正确入库")
        
    except Exception as e:
        safe_print(f"验证失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify_order_item_ingestion_fix()

