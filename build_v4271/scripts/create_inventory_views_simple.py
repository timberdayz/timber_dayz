#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建库存物化视图（简化版）- 直接执行关键SQL语句
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

def main():
    db = next(get_db())
    
    try:
        safe_print("\n" + "="*70)
        safe_print("创建库存物化视图（简化版）")
        safe_print("="*70)
        
        # Step 1: DROP旧视图
        safe_print("\n[Step 1] 删除旧视图...")
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE"))
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_inventory_by_sku CASCADE"))
        db.commit()
        safe_print("[OK] 旧视图已删除")
        
        # Step 2: 创建mv_inventory_summary视图
        safe_print("\n[Step 2] 创建mv_inventory_summary视图...")
        create_summary_sql = """
        CREATE MATERIALIZED VIEW mv_inventory_summary AS
        SELECT
            p.platform_code,
            p.shop_id,
            COALESCE(p.warehouse, 'default') as warehouse,
            COUNT(DISTINCT p.platform_sku) as total_products,
            SUM(COALESCE(p.total_stock, p.stock, 0)) as total_quantity_on_hand,
            SUM(COALESCE(p.available_stock, p.stock, 0)) as total_quantity_available,
            SUM(COALESCE(p.reserved_stock, 0)) as total_quantity_reserved,
            SUM(COALESCE(p.in_transit_stock, 0)) as total_quantity_incoming,
            COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 1 END) as out_of_stock_count,
            COUNT(CASE WHEN COALESCE(p.available_stock, p.stock, 0) > 0 
                       AND COALESCE(p.available_stock, p.stock, 0) < 10 THEN 1 END) as low_stock_count,
            MAX(p.metric_date) as latest_snapshot_date,
            NOW() as last_refreshed_at
        FROM fact_product_metrics p
        WHERE p.data_domain = 'inventory'
          AND p.granularity = 'snapshot'
        GROUP BY p.platform_code, p.shop_id, COALESCE(p.warehouse, 'default')
        WITH DATA;
        """
        db.execute(text(create_summary_sql))
        db.commit()
        safe_print("[OK] mv_inventory_summary视图已创建")
        
        # Step 3: 创建mv_inventory_by_sku视图
        safe_print("\n[Step 3] 创建mv_inventory_by_sku视图...")
        create_sku_sql = """
        CREATE MATERIALIZED VIEW mv_inventory_by_sku AS
        SELECT
            p.id as metric_id,
            p.platform_code,
            p.shop_id,
            p.platform_sku,
            p.product_name,
            p.warehouse,
            p.image_url,  -- v4.10.0新增：产品图片URL
            COALESCE(p.total_stock, p.stock, 0) as total_stock,
            COALESCE(p.available_stock, p.stock, 0) as available_stock,
            COALESCE(p.reserved_stock, 0) as reserved_stock,
            COALESCE(p.in_transit_stock, 0) as in_transit_stock,
            CASE 
                WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
                ELSE 'high_stock'
            END as stock_status,
            p.metric_date,
            p.granularity,
            p.created_at,
            p.updated_at
        FROM fact_product_metrics p
        WHERE p.data_domain = 'inventory'
          AND p.granularity = 'snapshot'
          AND p.metric_date >= CURRENT_DATE - INTERVAL '90 days'
        WITH DATA;
        """
        db.execute(text(create_sku_sql))
        db.commit()
        safe_print("[OK] mv_inventory_by_sku视图已创建")
        
        # Step 4: 创建索引
        safe_print("\n[Step 4] 创建索引...")
        indexes = [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_summary_pk ON mv_inventory_summary (platform_code, shop_id, warehouse);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_platform ON mv_inventory_summary (platform_code);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_shop ON mv_inventory_summary (shop_id);",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_pk ON mv_inventory_by_sku (metric_id);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_platform_sku ON mv_inventory_by_sku (platform_code, platform_sku);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_date ON mv_inventory_by_sku (metric_date DESC);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_status ON mv_inventory_by_sku (stock_status);",
        ]
        
        for idx_sql in indexes:
            try:
                db.execute(text(idx_sql))
                db.commit()
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    safe_print(f"[WARN] 创建索引警告: {e}")
                    db.rollback()
        
        safe_print("[OK] 所有索引已创建")
        
        # Step 5: 验证视图
        safe_print("\n[Step 5] 验证视图...")
        result = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE matviewname IN ('mv_inventory_summary', 'mv_inventory_by_sku')
        """))
        views = [row[0] for row in result.fetchall()]
        
        if 'mv_inventory_summary' in views:
            safe_print("[OK] mv_inventory_summary视图存在")
        else:
            safe_print("[FAIL] mv_inventory_summary视图不存在")
        
        if 'mv_inventory_by_sku' in views:
            safe_print("[OK] mv_inventory_by_sku视图存在")
        else:
            safe_print("[FAIL] mv_inventory_by_sku视图不存在")
        
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] 库存物化视图创建完成！")
        safe_print("="*70)
        
    except Exception as e:
        db.rollback()
        safe_print(f"[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

