#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查DSS架构视图状态
检查Phase 1中定义的所有视图是否已在数据库中创建
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


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def check_views():
    """检查所有DSS视图状态"""
    safe_print("\n" + "=" * 70)
    safe_print("检查DSS架构视图状态（Phase 1）")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # Phase 1.2: Layer 1 原子视图（6个）
        expected_atomic_views = [
            'view_orders_atomic',
            'view_product_metrics_atomic',
            'view_inventory_atomic',
            'view_expenses_atomic',
            'view_targets_atomic',
            'view_campaigns_atomic',
        ]
        
        # Phase 1.4: Layer 2 聚合物化视图（3个新增）
        expected_aggregate_mvs = [
            'mv_daily_sales_summary',
            'mv_monthly_shop_performance',
            'mv_product_sales_ranking',
        ]
        
        # Phase 1.6: Layer 3 宽表视图（2个）
        expected_wide_views = [
            'view_shop_performance_wide',
            'view_product_performance_wide',
        ]
        
        # 查询所有视图
        all_views = db.execute(text("""
            SELECT viewname 
            FROM pg_views 
            WHERE schemaname = 'public' 
            ORDER BY viewname
        """)).fetchall()
        view_names = [v[0] for v in all_views]
        
        # 查询所有物化视图
        all_mvs = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public' 
            ORDER BY matviewname
        """)).fetchall()
        mv_names = [mv[0] for mv in all_mvs]
        
        # 检查原子视图
        safe_print("\n[Layer 1] 原子视图（6个）:")
        atomic_status = {}
        for view_name in expected_atomic_views:
            exists = view_name in view_names
            atomic_status[view_name] = exists
            if exists:
                try:
                    row_count = db.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
                    safe_print(f"  [OK] {view_name:35} - 存在 (行数: {row_count})")
                except Exception as e:
                    safe_print(f"  [ERROR] {view_name:35} - 存在但查询失败: {str(e)}")
            else:
                safe_print(f"  [MISSING] {view_name:35} - 不存在")
        
        # 检查聚合物化视图
        safe_print("\n[Layer 2] 聚合物化视图（3个新增）:")
        aggregate_status = {}
        for mv_name in expected_aggregate_mvs:
            exists = mv_name in mv_names
            aggregate_status[mv_name] = exists
            if exists:
                try:
                    row_count = db.execute(text(f"SELECT COUNT(*) FROM {mv_name}")).scalar()
                    safe_print(f"  [OK] {mv_name:35} - 存在 (行数: {row_count})")
                except Exception as e:
                    safe_print(f"  [ERROR] {mv_name:35} - 存在但查询失败: {str(e)}")
            else:
                safe_print(f"  [MISSING] {mv_name:35} - 不存在")
        
        # 检查宽表视图
        safe_print("\n[Layer 3] 宽表视图（2个）:")
        wide_status = {}
        for view_name in expected_wide_views:
            exists = view_name in view_names
            wide_status[view_name] = exists
            if exists:
                try:
                    row_count = db.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
                    safe_print(f"  [OK] {view_name:35} - 存在 (行数: {row_count})")
                except Exception as e:
                    safe_print(f"  [ERROR] {view_name:35} - 存在但查询失败: {str(e)}")
            else:
                safe_print(f"  [MISSING] {view_name:35} - 不存在")
        
        # 汇总
        safe_print("\n" + "=" * 70)
        safe_print("汇总:")
        total_expected = len(expected_atomic_views) + len(expected_aggregate_mvs) + len(expected_wide_views)
        total_exists = sum(atomic_status.values()) + sum(aggregate_status.values()) + sum(wide_status.values())
        safe_print(f"  预期视图数: {total_expected}")
        safe_print(f"  已创建视图数: {total_exists}")
        safe_print(f"  缺失视图数: {total_expected - total_exists}")
        
        if total_exists == total_expected:
            safe_print("\n[SUCCESS] 所有Phase 1视图已创建！")
            return True
        else:
            safe_print("\n[PENDING] 部分视图未创建，需要执行SQL文件")
            return False
        
    finally:
        db.close()


if __name__ == "__main__":
    check_views()

