#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证已创建的DSS视图是否正常工作
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
            # 检查视图是否存在
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
            safe_print(f"  [MISSING] {view_name} - 不存在")
            return False
        
        # 尝试查询视图
        try:
            row_count = db.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
            safe_print(f"  [OK] {view_name:35} - 存在，可查询 (行数: {row_count})")
            
            # 尝试查询前5行（如果有数据）
            if row_count > 0:
                sample = db.execute(text(f"SELECT * FROM {view_name} LIMIT 1")).fetchone()
                if sample:
                    safe_print(f"         - 示例数据字段数: {len(sample)}")
            
            return True
        except Exception as e:
            safe_print(f"  [ERROR] {view_name:35} - 存在但查询失败: {str(e)[:100]}")
            return False
            
    except Exception as e:
        safe_print(f"  [ERROR] {view_name:35} - 验证失败: {str(e)[:100]}")
        return False


def main():
    safe_print("\n" + "=" * 70)
    safe_print("验证已创建的DSS视图")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 已创建的视图列表
        created_views = [
            ('view_orders_atomic', 'view'),
            ('view_expenses_atomic', 'view'),
            ('mv_daily_sales_summary', 'materialized_view'),
        ]
        
        safe_print("\n验证视图:")
        success_count = 0
        for view_name, view_type in created_views:
            if validate_view(db, view_name, view_type):
                success_count += 1
        
        safe_print("\n" + "=" * 70)
        safe_print(f"验证结果: {success_count}/{len(created_views)} 个视图正常工作")
        
        if success_count == len(created_views):
            safe_print("\n[SUCCESS] 所有已创建的视图都正常工作！")
        else:
            safe_print(f"\n[WARN] {len(created_views) - success_count} 个视图存在问题")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

