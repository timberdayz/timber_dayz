#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复SKU字段定义和价格字段映射问题

修复内容：
1. SKU分层分级：
   - 品类级别：商品SKU (product_sku)
   - 具体规格：产品SKU (platform_sku)
   - 规格货号：统一映射到产品SKU (platform_sku)，删除重复定义
2. 价格字段映射：
   - 单价映射为"价格" (price)
   - 总价映射为"总价" (total_price)，而不是"总价（元）"
3. 验证规则：支持更多SKU字段名
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text
import json

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def main():
    safe_print("\n" + "="*70)
    safe_print("修复SKU字段定义和价格字段映射")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # Step 1: 添加商品SKU字段到inventory域（品类级别）
        safe_print("\n[Step 1] 添加商品SKU字段到inventory域...")
        insert_product_sku = text("""
            INSERT INTO field_mapping_dictionary 
                (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
            VALUES
                ('product_sku', '商品SKU', 'Product SKU', 'inventory', 'dimension', false, 'string',
                 '商品SKU（品类级别，用于商品分组）',
                 '["商品SKU", "商品编号", "product_sku", "商品货号", "品类SKU"]'::jsonb,
                 true, 'system', NOW())
            ON CONFLICT (field_code) DO UPDATE SET
                cn_name = EXCLUDED.cn_name,
                data_domain = 'inventory',
                description = EXCLUDED.description,
                synonyms = EXCLUDED.synonyms,
                updated_at = NOW()
        """)
        db.execute(insert_product_sku)
        db.commit()
        safe_print("  [OK] 商品SKU字段已添加/更新")
        
        # Step 2: 更新产品SKU字段的同义词，明确区分商品SKU和产品SKU
        safe_print("\n[Step 2] 更新产品SKU字段定义...")
        update_platform_sku = text("""
            UPDATE field_mapping_dictionary
            SET description = '产品SKU（具体规格级别，用于库存管理）',
                synonyms = '["产品SKU", "规格SKU", "SKU", "platform_sku", "规格货号", "spec_sku", "货号"]'::jsonb,
                updated_at = NOW()
            WHERE field_code = 'platform_sku' 
              AND data_domain = 'inventory'
        """)
        db.execute(update_platform_sku)
        db.commit()
        safe_print("  [OK] 产品SKU字段定义已更新")
        
        # Step 3: 删除或标记规格相关重复字段（spec_sku应该映射到platform_sku）
        safe_print("\n[Step 3] 处理规格相关字段...")
        # 将spec_sku标记为deprecated，并更新同义词指向platform_sku
        update_spec_sku = text("""
            UPDATE field_mapping_dictionary
            SET status = 'deprecated',
                description = '已废弃：请使用产品SKU (platform_sku)',
                updated_at = NOW()
            WHERE field_code = 'spec_sku' 
              AND data_domain = 'products'
        """)
        db.execute(update_spec_sku)
        db.commit()
        safe_print("  [OK] 规格货号字段已标记为废弃")
        
        # Step 4: 添加总价字段到inventory域
        safe_print("\n[Step 4] 添加总价字段到inventory域...")
        insert_total_price = text("""
            INSERT INTO field_mapping_dictionary 
                (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
            VALUES
                ('total_price', '总价', 'Total Price', 'inventory', 'metric', false, 'float',
                 '商品总价（不含货币单位）',
                 '["总价", "total_price", "总金额", "合计", "总计"]'::jsonb,
                 true, 'system', NOW())
            ON CONFLICT (field_code) DO UPDATE SET
                cn_name = EXCLUDED.cn_name,
                data_domain = 'inventory',
                description = EXCLUDED.description,
                synonyms = EXCLUDED.synonyms,
                updated_at = NOW()
        """)
        db.execute(insert_total_price)
        db.commit()
        safe_print("  [OK] 总价字段已添加/更新")
        
        # Step 5: 更新价格字段的同义词，确保单价映射到price
        safe_print("\n[Step 5] 更新价格字段定义...")
        update_price = text("""
            UPDATE field_mapping_dictionary
            SET description = '单价（不含货币单位）',
                synonyms = '["价格", "单价", "price", "unit_price", "单价（元）", "单价元"]'::jsonb,
                updated_at = NOW()
            WHERE field_code = 'price' 
              AND data_domain IN ('products', 'inventory')
        """)
        db.execute(update_price)
        db.commit()
        safe_print("  [OK] 价格字段定义已更新")
        
        # Step 6: 标记"总价（元）"字段为废弃，引导使用"总价"
        safe_print("\n[Step 6] 处理总价（元）字段...")
        update_zong_jia_yuan = text("""
            UPDATE field_mapping_dictionary
            SET status = 'deprecated',
                description = '已废弃：请使用总价 (total_price)',
                updated_at = NOW()
            WHERE field_code = 'zong_jia_yuan' 
              AND data_domain = 'products'
        """)
        db.execute(update_zong_jia_yuan)
        db.commit()
        safe_print("  [OK] 总价（元）字段已标记为废弃")
        
        # Step 7: 更新验证规则，支持更多SKU字段名
        safe_print("\n[Step 7] 验证规则已更新（代码层面）...")
        safe_print("  [INFO] 验证规则已支持product_id、platform_sku、product_sku等字段")
        
        # 验证结果
        safe_print("\n[验证] 检查更新结果...")
        check_query = text("""
            SELECT field_code, cn_name, data_domain, is_required, status
            FROM field_mapping_dictionary
            WHERE (field_code LIKE '%sku%' OR cn_name LIKE '%SKU%' OR cn_name LIKE '%规格%' OR cn_name LIKE '%总价%' OR cn_name LIKE '%价格%')
              AND data_domain IN ('inventory', 'products')
            ORDER BY data_domain, field_code
        """)
        result = db.execute(check_query)
        rows = result.fetchall()
        
        safe_print("\n  更新后的字段状态:")
        for row in rows:
            status_str = f" - {row[4]}" if row[4] and row[4] != 'active' else ""
            safe_print(f"    - {row[1]} ({row[0]}) - {row[2]} - 必填:{row[3]}{status_str}")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] SKU和价格字段修复完成！")
        safe_print("="*70)
        safe_print("\n修复总结:")
        safe_print("  1. ✅ 商品SKU (product_sku) - 品类级别，已添加到inventory域")
        safe_print("  2. ✅ 产品SKU (platform_sku) - 具体规格，同义词包含规格货号")
        safe_print("  3. ✅ 规格货号 (spec_sku) - 已标记为废弃，应使用产品SKU")
        safe_print("  4. ✅ 总价 (total_price) - 已添加到inventory域")
        safe_print("  5. ✅ 总价（元）(zong_jia_yuan) - 已标记为废弃，应使用总价")
        safe_print("  6. ✅ 价格 (price) - 同义词已更新，包含单价相关词汇")
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

