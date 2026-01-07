#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建mv_inventory_by_sku主视图（inventory域）

⭐ v4.12.0新增：创建inventory域主视图
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


def create_mv_inventory_by_sku():
    """创建mv_inventory_by_sku主视图"""
    safe_print("=" * 70)
    safe_print("创建mv_inventory_by_sku主视图（inventory域）")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 读取SQL文件
        sql_file = project_root / "sql" / "materialized_views" / "create_mv_inventory_by_sku_main_view.sql"
        
        if not sql_file.exists():
            safe_print(f"[ERROR] SQL文件不存在: {sql_file}")
            return False
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        safe_print("\n[1] 执行SQL创建物化视图...")
        
        # 先DROP视图（如果存在）
        safe_print("  [INFO] 先DROP现有视图（如果存在）...")
        try:
            db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_inventory_by_sku CASCADE"))
            db.commit()
            safe_print("  [OK] DROP视图成功")
        except Exception as e:
            safe_print(f"  [WARN] DROP视图失败（可能不存在）: {e}")
            db.rollback()
        
        # 执行SQL（按语句分割，跳过DROP语句）
        statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--') and 'DROP MATERIALIZED VIEW' not in s.upper()]
        
        for i, statement in enumerate(statements, 1):
            if statement:
                try:
                    db.execute(text(statement))
                    db.commit()
                    safe_print(f"  [OK] 执行语句 {i}/{len(statements)}")
                except Exception as e:
                    safe_print(f"  [ERROR] 执行语句 {i} 失败: {e}")
                    db.rollback()
                    return False
        
        # 验证视图创建成功
        safe_print("\n[2] 验证视图创建...")
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' AND matviewname = 'mv_inventory_by_sku'
            )
        """))
        
        if result.scalar():
            safe_print("[OK] 视图创建成功")
            
            # 检查唯一索引
            result = db.execute(text("""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'mv_inventory_by_sku' 
                AND indexdef LIKE '%UNIQUE%'
            """))
            
            if result.scalar() > 0:
                safe_print("[OK] 唯一索引创建成功")
            else:
                safe_print("[WARN] 唯一索引未创建")
            
            # 检查数据行数
            result = db.execute(text("SELECT COUNT(*) FROM mv_inventory_by_sku"))
            row_count = result.scalar()
            safe_print(f"[INFO] 视图包含 {row_count} 行数据")
            
            return True
        else:
            safe_print("[ERROR] 视图创建失败")
            return False
        
    except Exception as e:
        logger.error(f"创建视图失败: {e}", exc_info=True)
        safe_print(f"[ERROR] 创建失败: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = create_mv_inventory_by_sku()
    sys.exit(0 if success else 1)

