#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证所有DSS视图是否正常工作
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def validate_view(db, view_name: str, view_type: str = 'view'):
    """验证单个视图"""
    try:
        if view_type == 'view':
            result = db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_views 
                    WHERE schemaname = 'public' AND viewname = :view_name
                )
            """), {"view_name": view_name})
        else:  # materialized view
            result = db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_matviews 
                    WHERE schemaname = 'public' AND matviewname = :view_name
                )
            """), {"view_name": view_name})
        
        if not result.scalar():
            safe_print(f"  [MISSING] {view_name}")
            return False
        
        # 尝试查询视图
        try:
            row_count = db.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
            safe_print(f"  [OK] {view_name:40} - 存在，可查询 (行数: {row_count})")
            
            # 尝试查询前1行（如果有数据）
            if row_count > 0:
                sample = db.execute(text(f"SELECT * FROM {view_name} LIMIT 1")).fetchone()
                if sample:
                    safe_print(f"         - 示例数据字段数: {len(sample)}")
            
            return True
        except Exception as e:
            safe_print(f"  [ERROR] {view_name:40} - 存在但查询失败: {str(e)[:100]}")
            return False
            
    except Exception as e:
        safe_print(f"  [ERROR] {view_name:40} - 验证失败: {str(e)[:100]}")
        return False


def main():
    safe_print("\n" + "=" * 70)
    safe_print("验证所有DSS视图（Phase 1）")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 所有视图列表
        all_views = [
            # Layer 1: 原子视图
            ('view_orders_atomic', 'view'),
            ('view_product_metrics_atomic', 'view'),
            ('view_inventory_atomic', 'view'),
            ('view_expenses_atomic', 'view'),
            ('view_targets_atomic', 'view'),
            ('view_campaigns_atomic', 'view'),
            # Layer 2: 聚合物化视图
            ('mv_daily_sales_summary', 'materialized_view'),
            ('mv_monthly_shop_performance', 'materialized_view'),
            ('mv_product_sales_ranking', 'materialized_view'),
            # Layer 3: 宽表视图
            ('view_shop_performance_wide', 'view'),
            ('view_product_performance_wide', 'view'),
        ]
        
        safe_print("\n[Layer 1] 原子视图（6个）:")
        layer1_count = 0
        for view_name, view_type in all_views[:6]:
            if validate_view(db, view_name, view_type):
                layer1_count += 1
        
        safe_print("\n[Layer 2] 聚合物化视图（3个）:")
        layer2_count = 0
        for view_name, view_type in all_views[6:9]:
            if validate_view(db, view_name, view_type):
                layer2_count += 1
        
        safe_print("\n[Layer 3] 宽表视图（2个）:")
        layer3_count = 0
        for view_name, view_type in all_views[9:]:
            if validate_view(db, view_name, view_type):
                layer3_count += 1
        
        safe_print("\n" + "=" * 70)
        safe_print(f"验证结果:")
        safe_print(f"  Layer 1 (原子视图): {layer1_count}/6")
        safe_print(f"  Layer 2 (聚合物化视图): {layer2_count}/3")
        safe_print(f"  Layer 3 (宽表视图): {layer3_count}/2")
        safe_print(f"  总计: {layer1_count + layer2_count + layer3_count}/11")
        
        if layer1_count + layer2_count + layer3_count == 11:
            safe_print("\n[SUCCESS] 所有视图都正常工作！")
        else:
            safe_print(f"\n[WARN] {11 - (layer1_count + layer2_count + layer3_count)} 个视图存在问题")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

