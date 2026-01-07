#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查现有主视图是否符合主视图标准

⭐ v4.12.0新增：审查mv_product_management和mv_inventory_summary
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def review_main_view(db, view_name: str, data_domain: str, expected_fields: list):
    """审查主视图"""
    print(f"\n{'='*70}")
    print(f"审查主视图: {view_name} ({data_domain}域)")
    print(f"{'='*70}")
    
    try:
        # 1. 检查视图是否存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' AND matviewname = :view_name
            )
        """), {"view_name": view_name})
        
        if not result.scalar():
            print(f"[FAIL] 视图 {view_name} 不存在")
            return False
        
        print(f"[OK] 视图 {view_name} 存在")
        
        # 2. 检查唯一索引
        result = db.execute(text("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = :view_name 
            AND indexdef LIKE '%UNIQUE%'
        """), {"view_name": view_name})
        
        unique_index_count = result.scalar()
        if unique_index_count > 0:
            print(f"[OK] 视图有 {unique_index_count} 个唯一索引")
        else:
            print(f"[WARN] 视图缺少唯一索引（需要支持CONCURRENTLY刷新）")
        
        # 3. 检查字段（物化视图需要使用pg_attribute查询）
        result = db.execute(text("""
            SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'public'
            AND c.relname = :view_name
            AND a.attnum > 0
            AND NOT a.attisdropped
            ORDER BY a.attnum
        """), {"view_name": view_name})
        
        columns = {row[0]: row[1] for row in result.fetchall()}
        print(f"\n[INFO] 视图包含 {len(columns)} 个字段")
        
        # 4. 检查是否包含预期字段
        missing_fields = []
        for field in expected_fields:
            if field not in columns:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"[WARN] 缺少预期字段: {', '.join(missing_fields)}")
        else:
            print(f"[OK] 包含所有预期字段")
        
        # 5. 显示关键字段（根据数据域调整）
        print(f"\n[INFO] 关键字段列表:")
        if data_domain == 'inventory':
            # inventory域关键字段（不需要销售字段）
            key_fields = [
                'platform_code', 'shop_id', 'platform_sku', 
                'product_name', 'category', 'price', 'price_rmb',
                'total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock',
                'warehouse', 'stock_status', 'snapshot_date'
            ]
        else:
            # products域关键字段
            key_fields = [
                'platform_code', 'shop_id', 'platform_sku', 
                'product_name', 'category', 'price', 'price_rmb',
                'sales_volume', 'sales_amount', 'sales_amount_rmb',
                'stock', 'available_stock', 'page_views', 'conversion_rate'
            ]
        
        for field in key_fields:
            if field in columns:
                print(f"  [OK] {field} ({columns[field]})")
            else:
                print(f"  [MISS] {field}")
        
        # 6. 检查数据行数
        result = db.execute(text(f"SELECT COUNT(*) FROM {view_name}"))
        row_count = result.scalar()
        print(f"\n[INFO] 视图包含 {row_count} 行数据")
        
        return len(missing_fields) == 0 and unique_index_count > 0
        
    except Exception as e:
        logger.error(f"审查 {view_name} 失败: {e}", exc_info=True)
        print(f"[ERROR] 审查失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("审查现有主视图是否符合主视图标准")
    print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 审查mv_product_management（products域）
        products_expected_fields = [
            'platform_code', 'shop_id', 'platform_sku', 'product_name',
            'category', 'price', 'price_rmb', 'stock', 'available_stock',
            'sales_volume', 'sales_amount', 'sales_amount_rmb',
            'page_views', 'conversion_rate', 'rating', 'review_count',
            'metric_date', 'product_health_score'
        ]
        products_ok = review_main_view(
            db, 
            'mv_product_management', 
            'products',
            products_expected_fields
        )
        
        # 审查mv_inventory_by_sku（inventory域主视图）
        # ⚠️ 注意：inventory域不需要销售字段（sales_volume, sales_amount等）
        inventory_expected_fields = [
            'platform_code', 'shop_id', 'platform_sku', 'product_name',
            'total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock',
            'warehouse', 'snapshot_date', 'stock_status', 'price', 'price_rmb',
            'category', 'brand', 'specification', 'image_url'
        ]
        inventory_ok = review_main_view(
            db,
            'mv_inventory_by_sku',  # ⭐ v4.12.0修复：使用mv_inventory_by_sku作为inventory域主视图
            'inventory',
            inventory_expected_fields
        )
        
        # 总结
        print("\n" + "=" * 70)
        print("审查总结")
        print("=" * 70)
        
        if products_ok:
            print("[OK] mv_product_management 符合主视图标准")
        else:
            print("[WARN] mv_product_management 需要改进")
        
        if inventory_ok:
            print("[OK] mv_inventory_summary 符合主视图标准")
        else:
            print("[WARN] mv_inventory_summary 需要改进或创建")
        
        print("\n建议:")
        print("1. 主视图应包含数据域的所有核心字段")
        print("2. 主视图必须有唯一索引（支持CONCURRENTLY刷新）")
        print("3. 主视图应作为前端查询数据域信息的统一入口")
        
    except Exception as e:
        logger.error(f"审查过程出错: {e}", exc_info=True)
        print(f"\n[ERROR] 审查失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

