# -*- coding: utf-8 -*-
"""
重新查询并更新inventory域物化视图（包含所有最新标记的字段）
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

def update_inventory_mvs_with_all_fields():
    """更新库存物化视图，包含所有标记为is_mv_display=true的字段"""
    safe_print("=" * 80)
    safe_print("更新inventory域物化视图（包含所有标记字段）")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 查询所有is_mv_display=true的inventory域字段（包括表中不存在的，用于提示）
        safe_print("\n[1] 查询所有is_mv_display=true的inventory域字段...")
        all_mv_fields_sql = """
            SELECT d.field_code, d.cn_name, d.field_group, d.data_type,
                   CASE WHEN EXISTS (
                       SELECT 1 
                       FROM information_schema.columns c
                       WHERE c.table_name = 'fact_product_metrics'
                         AND c.column_name = d.field_code
                   ) THEN true ELSE false END as exists_in_table
            FROM field_mapping_dictionary d
            WHERE d.data_domain = 'inventory'
              AND d.active = true
              AND d.status = 'active'
              AND d.is_mv_display = true
            ORDER BY 
                CASE d.field_group
                    WHEN 'dimension' THEN 1
                    WHEN 'datetime' THEN 2
                    WHEN 'metric' THEN 3
                    ELSE 4
                END,
                d.field_code
        """
        all_fields_result = db.execute(text(all_mv_fields_sql)).fetchall()
        
        safe_print(f"\n所有标记为'物化视图需要显示内容'的字段 ({len(all_fields_result)}个):")
        safe_print("-" * 80)
        
        mv_fields = []
        missing_fields = []
        
        for row in all_fields_result:
            field_code, cn_name, field_group, data_type, exists_in_table = row
            if exists_in_table:
                mv_fields.append({
                    'field_code': field_code,
                    'cn_name': cn_name,
                    'field_group': field_group,
                    'data_type': data_type
                })
                safe_print(f"  ✓ {field_code:30} ({cn_name:20}) [{field_group:10}]")
            else:
                missing_fields.append(field_code)
                safe_print(f"  ✗ {field_code:30} ({cn_name:20}) [{field_group:10}] [表中不存在]")
        
        if missing_fields:
            safe_print(f"\n[WARNING] 以下字段标记为显示，但表中不存在，将跳过:")
            for field in missing_fields:
                safe_print(f"  - {field}")
        
        safe_print(f"\n实际将包含在物化视图中的字段: {len(mv_fields)}个")
        
        if len(mv_fields) == 0:
            safe_print("\n[ERROR] 没有可用的字段！请检查字段映射配置。")
            return
        
        # 2. 重新生成SQL（使用修复后的脚本逻辑）
        safe_print("\n[2] 重新生成物化视图SQL...")
        
        # 按分组分类字段
        dimension_fields = [f for f in mv_fields if f['field_group'] == 'dimension']
        datetime_fields = [f for f in mv_fields if f['field_group'] == 'datetime']
        metric_fields = [f for f in mv_fields if f['field_group'] == 'metric']
        other_fields = [f for f in mv_fields if f['field_group'] not in ['dimension', 'datetime', 'metric']]
        
        # 构建SELECT字段列表
        select_parts = []
        
        # 维度字段
        for field in dimension_fields:
            select_parts.append(f"    p.{field['field_code']}")
        
        # 日期时间字段
        for field in datetime_fields:
            select_parts.append(f"    p.{field['field_code']}")
        
        # 指标字段（库存字段使用COALESCE）
        for field in metric_fields:
            if field['field_code'] in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock', 'stock']:
                select_parts.append(f"    COALESCE(p.{field['field_code']}, 0) as {field['field_code']}")
            else:
                select_parts.append(f"    p.{field['field_code']}")
        
        # 其他字段
        for field in other_fields:
            select_parts.append(f"    p.{field['field_code']}")
        
        # 添加库存状态计算字段（作为单个字段）
        stock_status_field = """    CASE
        WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
        WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
        WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
        ELSE 'high_stock'
    END as stock_status"""
        select_parts.append(stock_status_field)
        
        select_clause = ",\n".join(select_parts)
        
        # 生成唯一索引字段
        pk_fields = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                pk_fields.append("COALESCE(warehouse, 'default')")
            else:
                pk_fields.append(field['field_code'])
        pk_fields.append("metric_date")
        pk_fields.append("platform_sku")
        
        # 生成mv_inventory_by_sku SQL
        mv_sku_sql = f"""-- ============================================================
-- SKU级库存明细视图（v4.10.2更新）
-- 说明: 只包含is_mv_display=true的字段
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
ON mv_inventory_by_sku (platform_code, platform_sku);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_date 
ON mv_inventory_by_sku (metric_date DESC);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_status 
ON mv_inventory_by_sku (stock_status);

COMMENT ON MATERIALIZED VIEW mv_inventory_by_sku IS 'SKU级库存明细视图（v4.10.2更新）- 只包含is_mv_display=true的字段';
"""
        
        # 生成mv_inventory_summary SQL
        group_by_parts = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                group_by_parts.append(f"COALESCE(p.{field['field_code']}, 'default')")
            else:
                group_by_parts.append(f"p.{field['field_code']}")
        
        summary_select_parts = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                summary_select_parts.append(f"    COALESCE(p.{field['field_code']}, 'default') as warehouse")
            else:
                summary_select_parts.append(f"    p.{field['field_code']}")
        
        summary_select_parts.append("    COUNT(DISTINCT p.platform_sku) as total_products")
        
        for field in metric_fields:
            if field['field_code'] in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock', 'stock']:
                summary_select_parts.append(f"    SUM(COALESCE(p.{field['field_code']}, 0)) as total_{field['field_code']}")
        
        summary_select_parts.append("    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 1 END) as out_of_stock_count")
        low_stock_count_field = """    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) > 0
               AND COALESCE(p.available_stock, p.stock, 0) < 10 THEN 1 END) as low_stock_count"""
        summary_select_parts.append(low_stock_count_field)
        summary_select_parts.append("    MAX(p.metric_date) as latest_snapshot_date")
        summary_select_parts.append("    NOW() as last_refreshed_at")
        
        summary_select_clause = ",\n".join(summary_select_parts)
        group_by_clause = ",\n    ".join(group_by_parts)
        
        summary_pk_fields = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                summary_pk_fields.append("COALESCE(warehouse, 'default')")
            else:
                summary_pk_fields.append(field['field_code'])
        
        mv_summary_sql = f"""-- ============================================================
-- 库存汇总视图（v4.10.2更新）
-- 说明: 只包含is_mv_display=true的字段
-- 字段数: {len(dimension_fields)}个维度字段 + 汇总统计字段
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE;

CREATE MATERIALIZED VIEW mv_inventory_summary AS
SELECT
{summary_select_clause}
FROM fact_product_metrics p
WHERE p.data_domain = 'inventory'
  AND p.granularity = 'snapshot'
GROUP BY {group_by_clause};

-- 创建唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_summary_pk 
ON mv_inventory_summary ({', '.join(summary_pk_fields)});

-- 创建查询索引
CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_platform 
ON mv_inventory_summary (platform_code);

CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_shop 
ON mv_inventory_summary (shop_id);

COMMENT ON MATERIALIZED VIEW mv_inventory_summary IS '库存汇总视图（v4.10.2更新）- 只包含is_mv_display=true的字段';
"""
        
        # 3. 执行SQL
        safe_print("\n[3] 执行SQL更新物化视图...")
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

COMMENT ON FUNCTION refresh_inventory_views() IS '刷新库存相关物化视图（v4.10.2更新）';
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
        
        # 4. 验证更新结果
        safe_print("\n[4] 验证更新结果...")
        verify_sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'mv_inventory_by_sku'
            ORDER BY ordinal_position
        """
        verify_result = db.execute(text(verify_sql)).fetchall()
        actual_columns = [row[0] for row in verify_result]
        
        safe_print(f"\nmv_inventory_by_sku视图字段数: {len(actual_columns)}个")
        safe_print("字段列表:")
        for col in actual_columns:
            safe_print(f"  - {col}")
        
        safe_print("\n" + "=" * 80)
        safe_print("更新完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        db.rollback()
        safe_print(f"更新失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    update_inventory_mvs_with_all_fields()

