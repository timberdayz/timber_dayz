# -*- coding: utf-8 -*-
"""
检查并修复库存物化视图问题
1. 添加product_name字段到字段映射字典（如果不存在）
2. 更新物化视图，优先显示核心字段（SKU、商品名称、数量）
3. 保留店铺ID和平台代码作为筛选维度，但不作为主要显示字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def fix_inventory_mv():
    """修复库存物化视图"""
    safe_print("=" * 80)
    safe_print("修复库存物化视图问题")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 检查product_name字段是否在字段映射字典中
        safe_print("\n[1] 检查product_name字段是否在字段映射字典中...")
        check_product_name_sql = """
            SELECT field_code, cn_name, field_group, is_mv_display, data_domain
            FROM field_mapping_dictionary
            WHERE field_code = 'product_name'
              AND active = true
              AND status = 'active'
        """
        product_name_result = db.execute(text(check_product_name_sql)).fetchone()
        
        if product_name_result:
            safe_print(f"[OK] product_name字段已存在:")
            safe_print(f"  - field_code: {product_name_result[0]}")
            safe_print(f"  - cn_name: {product_name_result[1]}")
            safe_print(f"  - field_group: {product_name_result[2]}")
            safe_print(f"  - is_mv_display: {product_name_result[3]}")
            safe_print(f"  - data_domain: {product_name_result[4]}")
            
            # 检查是否在inventory域中
            if product_name_result[4] != 'inventory':
                safe_print(f"\n[WARNING] product_name字段在{product_name_result[4]}域中，不在inventory域中！")
                safe_print("需要为inventory域添加product_name字段，或更新is_mv_display状态")
        else:
            safe_print("[WARNING] product_name字段不存在于字段映射字典中！")
            safe_print("需要添加product_name字段到inventory域")
        
        # 2. 检查inventory域中是否有product_name字段（可能在其他域）
        safe_print("\n[2] 检查所有数据域中的product_name字段...")
        all_product_name_sql = """
            SELECT field_code, cn_name, field_group, is_mv_display, data_domain
            FROM field_mapping_dictionary
            WHERE field_code = 'product_name'
              AND active = true
              AND status = 'active'
        """
        all_product_name_result = db.execute(text(all_product_name_sql)).fetchall()
        
        if all_product_name_result:
            safe_print("找到的product_name字段:")
            for row in all_product_name_result:
                safe_print(f"  - data_domain: {row[4]}, is_mv_display: {row[3]}, field_group: {row[2]}")
        
        # 3. 为inventory域添加product_name字段（如果不存在）
        safe_print("\n[3] 为inventory域添加product_name字段...")
        
        # 检查是否已存在inventory域的product_name
        check_inventory_product_name_sql = """
            SELECT COUNT(*) 
            FROM field_mapping_dictionary
            WHERE field_code = 'product_name'
              AND data_domain = 'inventory'
              AND active = true
              AND status = 'active'
        """
        exists_count = db.execute(text(check_inventory_product_name_sql)).scalar()
        
        if exists_count == 0:
            safe_print("[INFO] 为inventory域添加product_name字段...")
            insert_product_name_sql = """
                INSERT INTO field_mapping_dictionary 
                    (field_code, cn_name, en_name, data_domain, field_group, is_required, 
                     data_type, description, synonyms, is_mv_display, active, status, 
                     display_order, match_weight, created_by, created_at)
                VALUES 
                    ('product_name', '商品名称', 'Product Name', 'inventory', 'metric', false,
                     'string', '商品名称（库存视图核心字段）',
                     '["商品名称", "产品名称", "product_name", "name", "商品标题", "产品标题"]'::jsonb,
                     true, true, 'active', 10, 1.0, 'system', NOW())
                ON CONFLICT (field_code) DO UPDATE SET
                    data_domain = EXCLUDED.data_domain,
                    is_mv_display = true,
                    updated_at = NOW()
            """
            db.execute(text(insert_product_name_sql))
            db.commit()
            safe_print("[OK] product_name字段已添加到inventory域，并标记为MV显示")
        else:
            # 更新is_mv_display为true
            safe_print("[INFO] product_name字段已存在，更新is_mv_display为true...")
            update_product_name_sql = """
                UPDATE field_mapping_dictionary
                SET is_mv_display = true,
                    updated_at = NOW()
                WHERE field_code = 'product_name'
                  AND data_domain = 'inventory'
            """
            db.execute(text(update_product_name_sql))
            db.commit()
            safe_print("[OK] product_name字段已更新为MV显示")
        
        # 4. 重新生成物化视图（包含product_name，优先显示核心字段）
        safe_print("\n[4] 重新生成物化视图（优先显示核心字段）...")
        
        # 查询所有is_mv_display=true的inventory域字段
        mv_fields_sql = """
            SELECT d.field_code, d.cn_name, d.field_group, d.data_type
            FROM field_mapping_dictionary d
            WHERE d.data_domain = 'inventory'
              AND d.active = true
              AND d.status = 'active'
              AND d.is_mv_display = true
              AND EXISTS (
                  SELECT 1 
                  FROM information_schema.columns c
                  WHERE c.table_name = 'fact_product_metrics'
                    AND c.column_name = d.field_code
              )
            ORDER BY 
                -- 核心字段优先：SKU、商品名称、数量
                CASE d.field_code
                    WHEN 'platform_sku' THEN 1
                    WHEN 'product_name' THEN 2
                    WHEN 'total_stock' THEN 3
                    WHEN 'available_stock' THEN 4
                    WHEN 'reserved_stock' THEN 5
                    WHEN 'in_transit_stock' THEN 6
                    ELSE 10
                END,
                CASE d.field_group
                    WHEN 'dimension' THEN 1
                    WHEN 'datetime' THEN 2
                    WHEN 'metric' THEN 3
                    ELSE 4
                END,
                d.field_code
        """
        mv_fields_result = db.execute(text(mv_fields_sql)).fetchall()
        
        mv_fields = []
        for row in mv_fields_result:
            field_code, cn_name, field_group, data_type = row
            mv_fields.append({
                'field_code': field_code,
                'cn_name': cn_name,
                'field_group': field_group,
                'data_type': data_type
            })
        
        safe_print(f"\n物化视图将包含的字段 ({len(mv_fields)}个，按优先级排序):")
        for i, field in enumerate(mv_fields, 1):
            safe_print(f"  {i:2}. {field['field_code']:30} ({field['cn_name']:20}) [{field['field_group']:10}]")
        
        # 生成SQL（核心字段优先）
        select_parts = []
        
        # 核心字段优先：SKU、商品名称、数量
        core_fields = ['platform_sku', 'product_name', 'total_stock', 'available_stock', 
                      'reserved_stock', 'in_transit_stock']
        
        for field_code in core_fields:
            field = next((f for f in mv_fields if f['field_code'] == field_code), None)
            if field:
                if field_code in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock']:
                    select_parts.append(f"    COALESCE(p.{field_code}, 0) as {field_code}")
                else:
                    select_parts.append(f"    p.{field_code}")
        
        # 其他字段（维度字段放在后面）
        for field in mv_fields:
            if field['field_code'] not in core_fields:
                if field['field_code'] in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock']:
                    select_parts.append(f"    COALESCE(p.{field['field_code']}, 0) as {field['field_code']}")
                else:
                    select_parts.append(f"    p.{field['field_code']}")
        
        # 添加库存状态计算字段
        stock_status_field = """    CASE
        WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
        WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
        WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
        ELSE 'high_stock'
    END as stock_status"""
        select_parts.append(stock_status_field)
        
        select_clause = ",\n".join(select_parts)
        
        # 生成唯一索引字段
        pk_fields = ['platform_sku', 'metric_date']
        if any(f['field_code'] == 'warehouse' for f in mv_fields):
            pk_fields.append("COALESCE(warehouse, 'default')")
        
        mv_sku_sql = f"""-- ============================================================
-- SKU级库存明细视图（v4.10.2更新 - 核心字段优先）
-- 说明: 优先显示SKU、商品名称、数量等核心字段
-- 字段数: {len(mv_fields)}个核心字段 + 1个计算字段（stock_status）
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS mv_inventory_by_sku CASCADE;

CREATE MATERIALIZED VIEW mv_inventory_by_sku AS
SELECT
{select_clause}
FROM fact_product_metrics p
WHERE p.data_domain = 'inventory'
  AND p.granularity = 'snapshot'
  AND p.metric_date >= CURRENT_DATE - INTERVAL '90 days';

-- 创建唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_pk 
ON mv_inventory_by_sku ({', '.join(pk_fields)});

-- 创建查询索引
CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_platform_sku 
ON mv_inventory_by_sku (platform_sku);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_product_name 
ON mv_inventory_by_sku (product_name);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_date 
ON mv_inventory_by_sku (metric_date DESC);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_status 
ON mv_inventory_by_sku (stock_status);

COMMENT ON MATERIALIZED VIEW mv_inventory_by_sku IS 'SKU级库存明细视图（v4.10.2更新）- 核心字段优先：SKU、商品名称、数量';
"""
        
        # 5. 执行SQL
        safe_print("\n[5] 执行SQL更新物化视图...")
        try:
            db.execute(text(mv_sku_sql))
            db.commit()
            safe_print("[OK] 物化视图更新成功")
        except Exception as e:
            db.rollback()
            safe_print(f"[ERROR] 物化视图更新失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # 6. 验证更新结果
        safe_print("\n[6] 验证更新结果...")
        verify_sql = """
            SELECT a.attname
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE c.relname = 'mv_inventory_by_sku'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
        """
        verify_result = db.execute(text(verify_sql)).fetchall()
        actual_columns = [row[0] for row in verify_result]
        
        safe_print(f"\nmv_inventory_by_sku视图字段 ({len(actual_columns)}个):")
        for i, col in enumerate(actual_columns, 1):
            safe_print(f"  {i:2}. {col}")
        
        # 检查是否包含product_name
        if 'product_name' in actual_columns:
            safe_print("\n[OK] product_name字段已成功添加到物化视图！")
        else:
            safe_print("\n[WARNING] product_name字段未出现在物化视图中")
        
        safe_print("\n" + "=" * 80)
        safe_print("修复完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        db.rollback()
        safe_print(f"修复失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    fix_inventory_mv()

