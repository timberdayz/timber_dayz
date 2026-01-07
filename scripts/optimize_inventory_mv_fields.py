# -*- coding: utf-8 -*-
"""
优化库存数据域物化视图字段
1. 将platform_code、shop_id、granularity的is_mv_display设为false
2. 重新生成物化视图，只包含核心字段
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

def optimize_inventory_mv_fields():
    """优化库存物化视图字段"""
    safe_print("=" * 80)
    safe_print("优化库存数据域物化视图字段")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 将platform_code、shop_id、granularity的is_mv_display设为false
        safe_print("\n[1] 更新字段映射字典，将platform_code、shop_id、granularity设为不显示...")
        
        fields_to_hide = ['platform_code', 'shop_id', 'granularity']
        
        for field_code in fields_to_hide:
            update_sql = """
                UPDATE field_mapping_dictionary
                SET is_mv_display = false,
                    updated_at = NOW()
                WHERE field_code = :field_code
                  AND data_domain = 'inventory'
            """
            result = db.execute(text(update_sql), {"field_code": field_code})
            db.commit()
            safe_print(f"  [OK] {field_code}: is_mv_display = false")
        
        # 2. 查询is_mv_display=true的inventory域字段（只包含表中存在的字段）
        safe_print("\n[2] 查询is_mv_display=true的inventory域字段...")
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
                    WHEN 'warehouse' THEN 7
                    WHEN 'metric_date' THEN 8
                    ELSE 10
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
        
        safe_print(f"\n物化视图将包含的字段 ({len(mv_fields)}个，核心字段优先):")
        for i, field in enumerate(mv_fields, 1):
            safe_print(f"  {i:2}. {field['field_code']:30} ({field['cn_name']:20}) [{field['field_group']:10}]")
        
        if len(mv_fields) == 0:
            safe_print("\n[ERROR] 没有可用的字段！请检查字段映射配置。")
            return
        
        # 3. 生成物化视图SQL（核心字段优先）
        safe_print("\n[3] 生成物化视图SQL（核心字段优先）...")
        
        # 核心字段顺序
        core_field_order = ['platform_sku', 'product_name', 'total_stock', 'available_stock', 
                           'reserved_stock', 'in_transit_stock', 'warehouse', 'metric_date']
        
        # 按顺序构建SELECT字段列表
        select_parts = []
        processed_fields = set()
        
        # 先添加核心字段（按顺序）
        for field_code in core_field_order:
            field = next((f for f in mv_fields if f['field_code'] == field_code), None)
            if field:
                if field_code in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock']:
                    select_parts.append(f"    COALESCE(p.{field_code}, 0) as {field_code}")
                else:
                    select_parts.append(f"    p.{field_code}")
                processed_fields.add(field_code)
        
        # 再添加其他字段
        for field in mv_fields:
            if field['field_code'] not in processed_fields:
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
        
        # 生成唯一索引字段（只使用核心字段）
        pk_fields = ['platform_sku', 'metric_date']
        if any(f['field_code'] == 'warehouse' for f in mv_fields):
            pk_fields.append("COALESCE(warehouse, 'default')")
        
        mv_sku_sql = f"""-- ============================================================
-- SKU级库存明细视图（v4.10.2优化 - 公司级库存，移除平台/店铺字段）
-- 说明: 只包含核心字段（SKU、商品名称、数量、仓库）
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

-- 创建唯一索引（只使用核心字段）
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

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_warehouse 
ON mv_inventory_by_sku (warehouse);

COMMENT ON MATERIALIZED VIEW mv_inventory_by_sku IS 'SKU级库存明细视图（v4.10.2优化）- 公司级库存，核心字段：SKU、商品名称、数量';
"""
        
        # 4. 生成汇总视图SQL（移除platform_code和shop_id）
        safe_print("\n[4] 生成汇总视图SQL（按仓库汇总）...")
        
        # 汇总视图按仓库分组（不再按平台/店铺分组）
        mv_summary_sql = f"""-- ============================================================
-- 库存汇总视图（v4.10.2优化 - 公司级库存，按仓库汇总）
-- 说明: 按仓库维度汇总，不按平台/店铺分组
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE;

CREATE MATERIALIZED VIEW mv_inventory_summary AS
SELECT
    COALESCE(p.warehouse, 'default') as warehouse,
    COUNT(DISTINCT p.platform_sku) as total_products,
    SUM(COALESCE(p.total_stock, 0)) as total_total_stock,
    SUM(COALESCE(p.available_stock, 0)) as total_available_stock,
    SUM(COALESCE(p.reserved_stock, 0)) as total_reserved_stock,
    SUM(COALESCE(p.in_transit_stock, 0)) as total_in_transit_stock,
    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 1 END) as out_of_stock_count,
    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) > 0
               AND COALESCE(p.available_stock, p.stock, 0) < 10 THEN 1 END) as low_stock_count,
    MAX(p.metric_date) as latest_snapshot_date,
    NOW() as last_refreshed_at
FROM fact_product_metrics p
WHERE p.data_domain = 'inventory'
  AND p.granularity = 'snapshot'
GROUP BY COALESCE(p.warehouse, 'default');

-- 创建唯一索引（只使用仓库）
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_summary_pk 
ON mv_inventory_summary (warehouse);

-- 创建查询索引
CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_warehouse 
ON mv_inventory_summary (warehouse);

COMMENT ON MATERIALIZED VIEW mv_inventory_summary IS '库存汇总视图（v4.10.2优化）- 公司级库存，按仓库汇总';
"""
        
        # 5. 执行SQL
        safe_print("\n[5] 执行SQL更新物化视图...")
        full_sql = f"""{mv_sku_sql}

{mv_summary_sql}

-- ==================== 刷新函数 =====================
CREATE OR REPLACE FUNCTION refresh_inventory_views()
RETURNS TABLE(
    duration_seconds FLOAT,
    row_count INTEGER,
    success BOOLEAN
) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    duration FLOAT;
    rows INTEGER;
BEGIN
    start_time := clock_timestamp();
    
    -- 刷新库存汇总视图
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_inventory_summary;
    
    -- 刷新SKU明细视图
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_inventory_by_sku;
    
    end_time := clock_timestamp();
    duration := EXTRACT(EPOCH FROM (end_time - start_time));
    
    -- 获取行数
    SELECT COUNT(*) INTO rows FROM mv_inventory_summary;
    
    RETURN QUERY SELECT duration, rows, true;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_inventory_views() IS '刷新库存相关物化视图（v4.10.2优化）';
"""
        
        try:
            db.execute(text(full_sql))
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
        
        # 检查是否移除了platform_code、shop_id、granularity
        removed_fields = ['platform_code', 'shop_id', 'granularity']
        removed_count = sum(1 for field in removed_fields if field not in actual_columns)
        
        if removed_count == len(removed_fields):
            safe_print(f"\n[OK] 已成功移除平台/店铺字段: {removed_fields}")
        else:
            still_present = [f for f in removed_fields if f in actual_columns]
            if still_present:
                safe_print(f"\n[WARNING] 以下字段仍在视图中: {still_present}")
        
        # 检查核心字段是否存在
        core_fields = ['platform_sku', 'product_name', 'total_stock', 'available_stock']
        missing_core = [f for f in core_fields if f not in actual_columns]
        if not missing_core:
            safe_print("\n[OK] 所有核心字段都已包含在视图中")
        else:
            safe_print(f"\n[WARNING] 缺少核心字段: {missing_core}")
        
        safe_print("\n" + "=" * 80)
        safe_print("优化完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        db.rollback()
        safe_print(f"优化失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    optimize_inventory_mv_fields()

