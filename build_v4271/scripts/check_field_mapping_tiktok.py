# -*- coding: utf-8 -*-
"""
检查TikTok订单字段映射情况
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_field_mapping():
    """检查字段映射情况"""
    safe_print("=" * 70)
    safe_print("检查TikTok订单字段映射情况")
    safe_print("=" * 70)
    
    db = next(get_db())
    try:
        # 1. 检查字段映射辞典中的orders域字段
        safe_print("\n[1] 检查字段映射辞典中的orders域关键字段...")
        result = db.execute(text("""
            SELECT field_code, cn_name, en_name, synonyms
            FROM field_mapping_dictionary 
            WHERE data_domain = 'orders' 
              AND (field_code IN ('shop_id', 'currency', 'subtotal', 'shipping_fee', 'tax_amount', 'total_amount', 'order_date_local')
                   OR field_code LIKE '%amount%'
                   OR field_code LIKE '%currency%'
                   OR field_code LIKE '%shop%')
            ORDER BY field_code
            LIMIT 30
        """)).fetchall()
        
        safe_print("  关键字段映射:")
        for field_code, cn_name, en_name, synonyms in result:
            safe_print(f"    {field_code}: {cn_name} ({en_name})")
            if synonyms:
                safe_print(f"      同义词: {synonyms[:100]}...")
        
        # 2. 检查attributes中的字段名是否在辞典中
        safe_print("\n[2] 检查attributes中的字段名是否在辞典中...")
        attr_fields = db.execute(text("""
            SELECT DISTINCT jsonb_object_keys(attributes) as attr_key
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            LIMIT 20
        """)).fetchall()
        
        safe_print("  attributes中的字段（前20个）:")
        attr_field_list = [row[0] for row in attr_fields]
        for attr_field in attr_field_list:
            # 检查这个字段是否在辞典中
            mapping = db.execute(text("""
                SELECT field_code, cn_name
                FROM field_mapping_dictionary 
                WHERE data_domain = 'orders' 
                  AND (field_code = :field OR :field = ANY(synonyms))
                LIMIT 1
            """), {"field": attr_field}).fetchone()
            
            if mapping:
                safe_print(f"    {attr_field} -> {mapping[0]} ({mapping[1]}) [已映射]")
            else:
                safe_print(f"    {attr_field} -> [未映射]")
        
        # 3. 检查是否有paid_amount_mai_jia等字段的映射
        safe_print("\n[3] 检查TikTok特定字段的映射...")
        tiktok_fields = ['paid_amount_mai_jia', 'amount_cai_gou', 'actual_shipping_fee', 'currency']
        for field in tiktok_fields:
            mapping = db.execute(text("""
                SELECT field_code, cn_name, synonyms
                FROM field_mapping_dictionary 
                WHERE data_domain = 'orders' 
                  AND (field_code = :field OR :field = ANY(synonyms))
                LIMIT 1
            """), {"field": field}).fetchone()
            
            if mapping:
                safe_print(f"    {field} -> {mapping[0]} ({mapping[1]})")
            else:
                safe_print(f"    {field} -> [未找到映射]")
        
        # 4. 检查示例订单的attributes中的金额字段值
        safe_print("\n[4] 检查示例订单的attributes中的金额字段值...")
        sample = db.execute(text("""
            SELECT order_id, attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            LIMIT 1
        """)).fetchone()
        
        if sample:
            order_id, attrs = sample
            safe_print(f"  订单 {order_id}:")
            # 检查金额相关字段
            amount_fields = {
                'paid_amount_mai_jia': attrs.get('paid_amount_mai_jia'),
                'amount_cai_gou': attrs.get('amount_cai_gou'),
                'actual_shipping_fee': attrs.get('actual_shipping_fee'),
                'currency': attrs.get('currency'),
                'shop_id': attrs.get('shop_id'),
            }
            for field, value in amount_fields.items():
                if value is not None:
                    safe_print(f"    {field}: {value}")
                else:
                    safe_print(f"    {field}: (NULL)")
        
        safe_print("\n" + "=" * 70)
        safe_print("检查完成")
        safe_print("=" * 70)
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_field_mapping()

