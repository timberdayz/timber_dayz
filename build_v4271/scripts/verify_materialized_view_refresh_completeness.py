#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证物化视图刷新完整性
检查是否有视图遗漏，以及刷新顺序是否正确
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from backend.services.materialized_view_service import MaterializedViewService

def verify_mv_refresh():
    """验证物化视图刷新完整性"""
    db = SessionLocal()
    try:
        # 1. 查询数据库中的所有物化视图
        all_views = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """)).fetchall()
        
        db_view_names = [row[0] for row in all_views]
        print(f"[INFO] 数据库中存在 {len(db_view_names)} 个物化视图:")
        for name in db_view_names:
            print(f"  - {name}")
        
        # 2. 获取刷新顺序列表
        refresh_order = MaterializedViewService._get_refresh_order()
        print(f"\n[INFO] 刷新顺序列表包含 {len(refresh_order)} 个视图:")
        for name in refresh_order:
            print(f"  - {name}")
        
        # 3. 检查是否有遗漏的视图
        missing_in_order = [v for v in db_view_names if v not in refresh_order]
        missing_in_db = [v for v in refresh_order if v not in db_view_names]
        
        if missing_in_order:
            print(f"\n[WARNING] 数据库中有 {len(missing_in_order)} 个视图不在刷新顺序列表中:")
            for name in missing_in_order:
                print(f"  - {name}")
            print("[INFO] 这些视图会被自动添加到刷新队列末尾（代码已实现）")
        else:
            print("\n[OK] 所有数据库视图都在刷新顺序列表中")
        
        if missing_in_db:
            print(f"\n[WARNING] 刷新顺序列表中有 {len(missing_in_db)} 个视图不在数据库中:")
            for name in missing_in_db:
                print(f"  - {name}")
            print("[INFO] 这些视图会被自动跳过（代码已实现）")
        else:
            print("\n[OK] 刷新顺序列表中的所有视图都在数据库中")
        
        # 4. 检查每个视图的最后刷新时间
        print("\n[INFO] 物化视图刷新状态:")
        for view_name in db_view_names:
            try:
                # ⭐ 修复：使用独立连接查询，避免事务冲突
                from sqlalchemy import create_engine
                from backend.utils.config import get_settings
                settings = get_settings()
                temp_engine = create_engine(settings.DATABASE_URL)
                with temp_engine.connect() as temp_conn:
                    # 查询视图行数
                    row_count = temp_conn.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
                    
                    # 查询刷新日志（如果有，检查表是否存在）
                    try:
                        # 先检查mv_refresh_log表是否存在
                        log_exists = temp_conn.execute(text("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = 'mv_refresh_log'
                            )
                        """)).scalar()
                        
                        if log_exists:
                            # 检查created_at字段是否存在
                            has_created_at = temp_conn.execute(text("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.columns 
                                    WHERE table_schema = 'public' 
                                    AND table_name = 'mv_refresh_log'
                                    AND column_name = 'created_at'
                                )
                            """)).scalar()
                            
                            if has_created_at:
                                log = temp_conn.execute(text("""
                                    SELECT triggered_by, row_count, duration_seconds, created_at
                                    FROM mv_refresh_log
                                    WHERE view_name = :view_name
                                    ORDER BY created_at DESC
                                    LIMIT 1
                                """), {"view_name": view_name}).fetchone()
                                
                                if log:
                                    print(f"  {view_name}: {row_count}行, 最后刷新: {log[3]} (耗时{log[2]:.2f}秒)")
                                else:
                                    print(f"  {view_name}: {row_count}行, 无刷新记录")
                            else:
                                print(f"  {view_name}: {row_count}行, 刷新日志表缺少created_at字段")
                        else:
                            print(f"  {view_name}: {row_count}行, 刷新日志表不存在")
                    except Exception as log_error:
                        print(f"  {view_name}: {row_count}行, 查询刷新日志失败 - {log_error}")
            except Exception as e:
                print(f"  {view_name}: 查询失败 - {e}")
        
        # 5. 检查底层数据表的数据量
        print("\n[INFO] 底层数据表数据量:")
        fact_tables = ['fact_orders', 'fact_order_items', 'fact_product_metrics']
        from sqlalchemy import create_engine
        from backend.utils.config import get_settings
        settings = get_settings()
        temp_engine = create_engine(settings.DATABASE_URL)
        for table_name in fact_tables:
            try:
                # ⭐ 修复：使用独立连接查询，避免事务冲突
                with temp_engine.connect() as temp_conn:
                    count = temp_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                    print(f"  {table_name}: {count}行")
            except Exception as e:
                print(f"  {table_name}: 查询失败 - {e}")
        
        # 6. 检查刷新顺序是否符合依赖关系
        print("\n[INFO] 刷新顺序验证:")
        layer1_b_class = [
            MaterializedViewService.VIEW_DAILY_SALES,
            MaterializedViewService.VIEW_ORDER_SALES_SUMMARY,
            MaterializedViewService.VIEW_SALES_DAY_SHOP_SKU,
            MaterializedViewService.VIEW_PRODUCT_MANAGEMENT,
            MaterializedViewService.VIEW_INVENTORY_SUMMARY,
            MaterializedViewService.VIEW_INVENTORY_BY_SKU,
        ]
        
        layer1_5_c_class = [
            MaterializedViewService.VIEW_SHOP_DAILY_PERFORMANCE,
            MaterializedViewService.VIEW_CAMPAIGN_ACHIEVEMENT,
            MaterializedViewService.VIEW_TARGET_ACHIEVEMENT,
            MaterializedViewService.VIEW_SHOP_HEALTH_SUMMARY,
        ]
        
        # 检查Layer 1是否在Layer 1.5之前
        layer1_indices = []
        layer1_5_indices = []
        
        for view in layer1_b_class:
            if view in refresh_order:
                layer1_indices.append(refresh_order.index(view))
        
        for view in layer1_5_c_class:
            if view in refresh_order:
                layer1_5_indices.append(refresh_order.index(view))
        
        if layer1_indices and layer1_5_indices:
            max_layer1 = max(layer1_indices)
            min_layer1_5 = min(layer1_5_indices)
            
            if max_layer1 < min_layer1_5:
                print("[OK] Layer 1（B类数据）在Layer 1.5（C类数据）之前刷新，符合依赖关系")
            else:
                print("[WARNING] Layer 1（B类数据）在Layer 1.5（C类数据）之后刷新，可能违反依赖关系")
        
    except Exception as e:
        print(f"[ERROR] 验证失败: {e}", exc_info=True)
    finally:
        db.close()

if __name__ == '__main__':
    verify_mv_refresh()

