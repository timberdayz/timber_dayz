# -*- coding: utf-8 -*-
"""
更新inventory域物化视图SQL文件（v4.10.2）
根据is_mv_display=true的字段生成物化视图定义
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

def generate_inventory_mv_sql():
    """生成库存物化视图SQL"""
    safe_print("=" * 80)
    safe_print("生成inventory域物化视图SQL（v4.10.2）")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 查询is_mv_display=true的inventory域字段（只包含表中存在的字段）
        safe_print("\n[1] 查询is_mv_display=true的inventory域字段...")
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
        
        safe_print(f"\n物化视图应包含的字段 ({len(mv_fields)}个):")
        for field in mv_fields:
            safe_print(f"  - {field['field_code']} ({field['cn_name']}) [{field['field_group']}]")
        
        # 2. 生成mv_inventory_by_sku SQL
        safe_print("\n[2] 生成mv_inventory_by_sku SQL...")
        
        # 按分组分类字段
        dimension_fields = [f for f in mv_fields if f['field_group'] == 'dimension']
        datetime_fields = [f for f in mv_fields if f['field_group'] == 'datetime']
        metric_fields = [f for f in mv_fields if f['field_group'] == 'metric']
        
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
            if field['field_code'] in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock']:
                select_parts.append(f"    COALESCE(p.{field['field_code']}, 0) as {field['field_code']}")
            else:
                select_parts.append(f"    p.{field['field_code']}")
        
        # 添加库存状态计算字段
        select_parts.append("    CASE")
        select_parts.append("        WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'")
        select_parts.append("        WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'")
        select_parts.append("        WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'")
        select_parts.append("        ELSE 'high_stock'")
        select_parts.append("    END as stock_status")
        
        select_clause = ",\n".join(select_parts)
        
        # 生成唯一索引字段（维度字段）
        pk_fields = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                pk_fields.append("COALESCE(warehouse, 'default')")
            else:
                pk_fields.append(field['field_code'])
        pk_fields.append("metric_date")  # 添加日期字段
        pk_fields.append("platform_sku")  # 添加SKU字段
        
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
        
        # 3. 生成mv_inventory_summary SQL
        safe_print("\n[3] 生成mv_inventory_summary SQL...")
        
        # GROUP BY字段（维度字段）
        group_by_parts = []
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                group_by_parts.append(f"COALESCE(p.{field['field_code']}, 'default')")
            else:
                group_by_parts.append(f"p.{field['field_code']}")
        
        # SELECT字段（汇总视图）
        summary_select_parts = []
        
        # 维度字段
        for field in dimension_fields:
            if field['field_code'] == 'warehouse':
                summary_select_parts.append(f"    COALESCE(p.{field['field_code']}, 'default') as warehouse")
            else:
                summary_select_parts.append(f"    p.{field['field_code']}")
        
        # 汇总字段
        summary_select_parts.append("    COUNT(DISTINCT p.platform_sku) as total_products")
        
        # 聚合库存指标字段
        for field in metric_fields:
            if field['field_code'] in ['total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock']:
                summary_select_parts.append(f"    SUM(COALESCE(p.{field['field_code']}, 0)) as total_{field['field_code']}")
        
        # 低库存告警
        summary_select_parts.append("    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 1 END) as out_of_stock_count")
        summary_select_parts.append("    COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) > 0")
        summary_select_parts.append("               AND COALESCE(p.available_stock, p.stock, 0) < 10 THEN 1 END) as low_stock_count")
        
        # 最新快照日期
        summary_select_parts.append("    MAX(p.metric_date) as latest_snapshot_date")
        
        # 统计信息
        summary_select_parts.append("    NOW() as last_refreshed_at")
        
        summary_select_clause = ",\n".join(summary_select_parts)
        group_by_clause = ",\n    ".join(group_by_parts)
        
        # 汇总视图的唯一索引字段
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
        
        # 4. 保存SQL文件
        safe_print("\n[4] 保存SQL文件...")
        sql_file_path = project_root / "sql" / "materialized_views" / "create_inventory_views_v4_10_2.sql"
        sql_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        full_sql = f"""-- ============================================================
-- 库存数据域物化视图（v4.10.2更新）
-- 时间: 2025-11-09
-- 版本: v4.10.2
-- 说明: 根据is_mv_display=true的字段自动生成
-- 字段数: {len(mv_fields)}个核心字段
-- ============================================================

{mv_sku_sql}

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

-- 完成提示
SELECT '库存物化视图创建成功（v4.10.2）！' as status;
"""
        
        with open(sql_file_path, 'w', encoding='utf-8') as f:
            f.write(full_sql)
        
        safe_print(f"[OK] SQL文件已保存: {sql_file_path}")
        
        # 5. 执行SQL
        safe_print("\n[5] 执行SQL更新物化视图...")
        try:
            db.execute(text(full_sql))
            db.commit()
            safe_print("[OK] 物化视图更新成功")
        except Exception as e:
            db.rollback()
            safe_print(f"[ERROR] 物化视图更新失败: {e}")
            import traceback
            traceback.print_exc()
            safe_print("\n请手动执行SQL文件:")
            safe_print(f"  psql -U postgres -d your_database -f {sql_file_path}")
        
        # 6. 验证更新结果
        safe_print("\n[6] 验证更新结果...")
        verify_sql = """
            SELECT 
                matviewname,
                (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = matviewname) as column_count
            FROM pg_matviews
            WHERE schemaname = 'public'
              AND matviewname IN ('mv_inventory_by_sku', 'mv_inventory_summary')
        """
        verify_result = db.execute(text(verify_sql)).fetchall()
        
        safe_print("\n更新后的视图字段数:")
        for row in verify_result:
            view_name, col_count = row
            safe_print(f"  - {view_name}: {col_count}个字段")
        
        safe_print("\n" + "=" * 80)
        safe_print("完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        db.rollback()
        safe_print(f"生成失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    generate_inventory_mv_sql()

