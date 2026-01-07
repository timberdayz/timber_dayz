#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执行物化视图SQL脚本
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

def execute_sql_statements(db, sql_content):
    """执行SQL语句列表"""
    statements = []
    current_stmt = []
    
    for line in sql_content.split('\n'):
        line = line.strip()
        if not line or line.startswith('--'):
            continue
        
        current_stmt.append(line)
        
        if line.endswith(';'):
            stmt = ' '.join(current_stmt)
            if stmt.strip():
                statements.append(stmt)
            current_stmt = []
    
    # 处理最后一个语句（如果没有分号）
    if current_stmt:
        stmt = ' '.join(current_stmt)
        if stmt.strip():
            statements.append(stmt)
    
    for stmt in statements:
        try:
            db.execute(text(stmt))
            safe_print(f"[OK] Executed: {stmt[:50]}...")
        except Exception as e:
            if 'already exists' not in str(e).lower() and 'duplicate' not in str(e).lower():
                safe_print(f"[WARN] {e}")

def main():
    db = next(get_db())
    try:
        # 1. 创建库存视图
        safe_print("\n[Step 1] 创建库存物化视图...")
        sql_file = Path("sql/materialized_views/create_inventory_views.sql")
        if sql_file.exists():
            sql_content = sql_file.read_text(encoding='utf-8')
            execute_sql_statements(db, sql_content)
            db.commit()
            safe_print("[OK] 库存视图创建完成")
        else:
            safe_print(f"[FAIL] SQL文件不存在: {sql_file}")
        
        # 2. 更新产品管理视图
        safe_print("\n[Step 2] 更新产品管理物化视图...")
        # 先DROP旧视图
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_product_management CASCADE"))
        db.commit()
        
        # 重新创建
        sql_file = Path("sql/create_mv_product_management.sql")
        if sql_file.exists():
            sql_content = sql_file.read_text(encoding='utf-8')
            execute_sql_statements(db, sql_content)
            db.commit()
            safe_print("[OK] 产品管理视图更新完成")
        else:
            safe_print(f"[FAIL] SQL文件不存在: {sql_file}")
        
    except Exception as e:
        db.rollback()
        safe_print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
