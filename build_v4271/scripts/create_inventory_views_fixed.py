#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建物化视图（修复版）- 正确处理SQL语句分割
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text
import re

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def execute_sql_file(db, file_path: Path):
    """执行SQL文件，正确处理函数定义"""
    if not file_path.exists():
        safe_print(f"[SKIP] SQL文件不存在: {file_path}")
        return False
    
    try:
        sql_content = file_path.read_text(encoding='utf-8')
        
        # 先DROP旧视图
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE"))
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_inventory_by_sku CASCADE"))
        db.commit()
        
        # 提取CREATE MATERIALIZED VIEW语句（到WITH DATA为止）
        # 匹配模式：CREATE MATERIALIZED VIEW ... WITH DATA;
        mv_pattern = r'CREATE MATERIALIZED VIEW[^;]+WITH DATA;'
        matches = re.findall(mv_pattern, sql_content, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            # 清理注释
            cleaned = re.sub(r'--[^\n]*', '', match)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            cleaned = cleaned.strip()
            
            if cleaned:
                try:
                    db.execute(text(cleaned))
                    db.commit()
                    safe_print(f"[OK] 创建物化视图成功")
                except Exception as e:
                    if 'already exists' not in str(e).lower():
                        safe_print(f"[WARN] 创建视图警告: {e}")
                        db.rollback()
        
        # 创建索引（单独执行）
        index_statements = [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_summary_pk ON mv_inventory_summary (platform_code, shop_id, warehouse);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_platform ON mv_inventory_summary (platform_code);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_summary_shop ON mv_inventory_summary (shop_id);",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_pk ON mv_inventory_by_sku (metric_id);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_platform_sku ON mv_inventory_by_sku (platform_code, platform_sku);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_date ON mv_inventory_by_sku (metric_date DESC);",
            "CREATE INDEX IF NOT EXISTS idx_mv_inventory_by_sku_status ON mv_inventory_by_sku (stock_status);",
        ]
        
        for idx_sql in index_statements:
            try:
                db.execute(text(idx_sql))
                db.commit()
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    safe_print(f"[WARN] 创建索引警告: {e}")
                    db.rollback()
        
        safe_print(f"[OK] 执行SQL文件: {file_path.name}")
        return True
        
    except Exception as e:
        db.rollback()
        safe_print(f"[FAIL] 执行SQL文件失败 {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    safe_print("\n" + "="*70)
    safe_print("创建库存物化视图")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 创建库存视图
        sql_file = Path("sql/materialized_views/create_inventory_views.sql")
        if sql_file.exists():
            execute_sql_file(db, sql_file)
        else:
            safe_print(f"[FAIL] SQL文件不存在: {sql_file}")
        
        # 验证视图是否创建成功
        result = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE matviewname IN ('mv_inventory_summary', 'mv_inventory_by_sku')
        """))
        views = [row[0] for row in result.fetchall()]
        
        if 'mv_inventory_summary' in views:
            safe_print("[OK] mv_inventory_summary视图已创建")
        if 'mv_inventory_by_sku' in views:
            safe_print("[OK] mv_inventory_by_sku视图已创建")
        
    except Exception as e:
        db.rollback()
        safe_print(f"[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

