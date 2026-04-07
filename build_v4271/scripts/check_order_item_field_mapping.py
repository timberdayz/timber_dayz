#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查订单明细字段映射，确认字段是否正确映射
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

def check_order_item_field_mapping():
    safe_print("======================================================================")
    safe_print("检查订单明细字段映射")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 检查字段映射字典中是否有订单明细字段
        safe_print("\n[1] 检查字段映射字典中的订单明细字段...")
        order_item_fields = db.execute(text("""
            SELECT field_code, cn_name, en_name, data_domain, is_required
            FROM field_mapping_dictionary 
            WHERE data_domain = 'orders'
              AND (
                field_code LIKE '%sku%' OR
                field_code LIKE '%quantity%' OR
                field_code LIKE '%qty%' OR
                field_code LIKE '%line_amount%' OR
                field_code LIKE '%unit_price%' OR
                cn_name LIKE '%SKU%' OR
                cn_name LIKE '%数量%' OR
                cn_name LIKE '%金额%' OR
                cn_name LIKE '%单价%'
              )
            ORDER BY field_code
        """)).fetchall()
        
        safe_print(f"  找到 {len(order_item_fields)} 个订单明细相关字段:")
        for f in order_item_fields:
            safe_print(f"    - {f[1]} ({f[0]}) - 必填:{f[4]}")
        
        # 2. 检查TikTok订单模板中的字段映射
        safe_print("\n[2] 检查TikTok订单模板中的字段映射...")
        template = db.execute(text("""
            SELECT t.id, t.template_name, t.header_row
            FROM field_mapping_templates t
            WHERE t.platform = 'tiktok' 
              AND t.data_domain = 'orders'
            ORDER BY t.id DESC
            LIMIT 1
        """)).fetchone()
        
        if template:
            template_id, template_name, header_row = template
            safe_print(f"  模板: {template_name} (ID={template_id}, header_row={header_row})")
            
            # 查询模板中的字段映射
            mappings = db.execute(text("""
                SELECT original_column, standard_field
                FROM field_mapping_template_items
                WHERE template_id = :template_id
                ORDER BY original_column
            """), {"template_id": template_id}).fetchall()
            
            safe_print(f"  模板中的字段映射 ({len(mappings)} 个):")
            sku_mappings = [m for m in mappings if 'sku' in m[0].lower() or 'sku' in m[1].lower()]
            qty_mappings = [m for m in mappings if '数量' in m[0] or 'quantity' in m[0].lower() or 'qty' in m[0].lower()]
            amount_mappings = [m for m in mappings if '金额' in m[0] or 'amount' in m[0].lower() or '价格' in m[0]]
            
            safe_print(f"\n  SKU相关映射 ({len(sku_mappings)} 个):")
            for m in sku_mappings[:10]:  # 只显示前10个
                safe_print(f"    {m[0]} → {m[1]}")
            
            safe_print(f"\n  数量相关映射 ({len(qty_mappings)} 个):")
            for m in qty_mappings[:10]:
                safe_print(f"    {m[0]} → {m[1]}")
            
            safe_print(f"\n  金额相关映射 ({len(amount_mappings)} 个):")
            for m in amount_mappings[:10]:
                safe_print(f"    {m[0]} → {m[1]}")
        
        # 3. 检查最近入库的订单数据，看看是否有订单明细字段
        safe_print("\n[3] 检查最近入库的订单数据（attributes字段）...")
        sample_order = db.execute(text("""
            SELECT order_id, attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            ORDER BY created_at DESC
            LIMIT 1
        """)).fetchone()
        
        if sample_order and sample_order[1]:
            attrs = sample_order[1]
            safe_print(f"  示例订单 order_id={sample_order[0]}")
            safe_print(f"  attributes中的字段: {list(attrs.keys())[:20] if isinstance(attrs, dict) else 'N/A'}...")
            
            # 检查是否有SKU相关字段
            sku_keys = [k for k in attrs.keys() if 'sku' in str(k).lower() or '商品' in str(k) or '产品' in str(k)] if isinstance(attrs, dict) else []
            qty_keys = [k for k in attrs.keys() if '数量' in str(k) or 'quantity' in str(k).lower() or 'qty' in str(k).lower()] if isinstance(attrs, dict) else []
            amount_keys = [k for k in attrs.keys() if '金额' in str(k) or 'amount' in str(k).lower() or '价格' in str(k)] if isinstance(attrs, dict) else []
            
            safe_print(f"\n  attributes中的SKU相关字段: {sku_keys[:10]}")
            safe_print(f"  attributes中的数量相关字段: {qty_keys[:10]}")
            safe_print(f"  attributes中的金额相关字段: {amount_keys[:10]}")
        
        safe_print("\n======================================================================")
        safe_print("检查完成")
        safe_print("======================================================================")
        safe_print("\n关键发现:")
        safe_print("  - 如果字段映射中没有platform_sku/quantity/line_amount等字段，")
        safe_print("    这些字段会被放入attributes JSON中")
        safe_print("  - 订单明细入库逻辑需要从r（原始数据）中提取这些字段")
        safe_print("  - 如果字段映射正确，重新入库数据后应该能看到订单明细数据")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_order_item_field_mapping()

