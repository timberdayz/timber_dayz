#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建DSS架构视图（Phase 1）
按依赖顺序执行SQL文件：原子视图 → 聚合视图 → 宽表视图
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


def execute_sql_file(db, sql_file: Path):
    """执行SQL文件"""
    safe_print(f"\n执行SQL文件: {sql_file.name}")
    
    try:
        sql_content = sql_file.read_text(encoding='utf-8')
        
        # 分割SQL语句（按分号分割，但保留注释）
        statements = []
        current_statement = []
        
        for line in sql_content.split('\n'):
            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('--') or not stripped:
                continue
            
            current_statement.append(line)
            
            # 如果行以分号结尾，说明是一个完整的SQL语句
            if stripped.endswith(';'):
                statement = '\n'.join(current_statement)
                if statement.strip():
                    statements.append(statement)
                current_statement = []
        
        # 执行所有SQL语句
        success_count = 0
        error_count = 0
        
        for i, statement in enumerate(statements, 1):
            try:
                db.execute(text(statement))
                db.commit()
                success_count += 1
            except Exception as e:
                error_count += 1
                safe_print(f"  [ERROR] 语句 {i} 执行失败: {str(e)[:100]}")
                # 继续执行其他语句
                db.rollback()
        
        if error_count == 0:
            safe_print(f"  [OK] 成功执行 {success_count} 个SQL语句")
            return True
        else:
            safe_print(f"  [WARN] 成功 {success_count} 个，失败 {error_count} 个")
            return False
            
    except Exception as e:
        safe_print(f"  [ERROR] 读取或执行SQL文件失败: {str(e)}")
        db.rollback()
        return False


def create_dss_views():
    """创建所有DSS视图"""
    safe_print("\n" + "=" * 70)
    safe_print("创建DSS架构视图（Phase 1）")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        sql_dir = project_root / "sql" / "views"
        
        # Phase 1.2: Layer 1 原子视图（按依赖顺序）
        atomic_views = [
            'atomic/view_orders_atomic.sql',
            'atomic/view_product_metrics_atomic.sql',
            'atomic/view_inventory_atomic.sql',
            'atomic/view_expenses_atomic.sql',
            'atomic/view_targets_atomic.sql',
            'atomic/view_campaigns_atomic.sql',
        ]
        
        # Phase 1.4: Layer 2 聚合物化视图
        aggregate_mvs = [
            'aggregate/mv_daily_sales_summary.sql',
            'aggregate/mv_monthly_shop_performance.sql',
            'aggregate/mv_product_sales_ranking.sql',
        ]
        
        # Phase 1.6: Layer 3 宽表视图
        wide_views = [
            'wide/view_shop_performance_wide.sql',
            'wide/view_product_performance_wide.sql',
        ]
        
        # 执行原子视图
        safe_print("\n" + "-" * 70)
        safe_print("[Layer 1] 创建原子视图（6个）")
        safe_print("-" * 70)
        atomic_success = 0
        for view_file in atomic_views:
            sql_file = sql_dir / view_file
            if sql_file.exists():
                if execute_sql_file(db, sql_file):
                    atomic_success += 1
            else:
                safe_print(f"  [MISSING] SQL文件不存在: {view_file}")
        
        # 执行聚合物化视图
        safe_print("\n" + "-" * 70)
        safe_print("[Layer 2] 创建聚合物化视图（3个）")
        safe_print("-" * 70)
        aggregate_success = 0
        for mv_file in aggregate_mvs:
            sql_file = sql_dir / mv_file
            if sql_file.exists():
                if execute_sql_file(db, sql_file):
                    aggregate_success += 1
            else:
                safe_print(f"  [MISSING] SQL文件不存在: {mv_file}")
        
        # 执行宽表视图
        safe_print("\n" + "-" * 70)
        safe_print("[Layer 3] 创建宽表视图（2个）")
        safe_print("-" * 70)
        wide_success = 0
        for view_file in wide_views:
            sql_file = sql_dir / view_file
            if sql_file.exists():
                if execute_sql_file(db, sql_file):
                    wide_success += 1
            else:
                safe_print(f"  [MISSING] SQL文件不存在: {view_file}")
        
        # 汇总
        safe_print("\n" + "=" * 70)
        safe_print("创建结果汇总:")
        safe_print(f"  原子视图: {atomic_success}/6")
        safe_print(f"  聚合物化视图: {aggregate_success}/3")
        safe_print(f"  宽表视图: {wide_success}/2")
        safe_print(f"  总计: {atomic_success + aggregate_success + wide_success}/11")
        
        total_expected = 11
        total_success = atomic_success + aggregate_success + wide_success
        
        if total_success == total_expected:
            safe_print("\n[SUCCESS] 所有视图创建成功！")
            return True
        else:
            safe_print(f"\n[WARN] 部分视图创建失败（{total_expected - total_success}个）")
            return False
        
    finally:
        db.close()


if __name__ == "__main__":
    success = create_dss_views()
    sys.exit(0 if success else 1)

