#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建mv_order_summary物化视图（orders域主视图）

使用方法：
    python scripts/create_mv_order_summary.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows兼容的安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def create_mv_order_summary():
    """创建mv_order_summary物化视图"""
    safe_print("=" * 70)
    safe_print("创建mv_order_summary物化视图")
    safe_print("=" * 70)
    
    # 读取SQL文件
    sql_file = project_root / "sql" / "materialized_views" / "create_mv_order_summary.sql"
    
    if not sql_file.exists():
        safe_print(f"[ERROR] SQL文件不存在: {sql_file}")
        return False
    
    safe_print(f"\n[1] 读取SQL文件: {sql_file}")
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # 分割SQL语句（按分号分割，但保留在字符串中的分号）
    statements = []
    current_statement = ""
    in_string = False
    string_char = None
    
    for char in sql_content:
        if char in ("'", '"') and (not current_statement or current_statement[-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        elif char == ';' and not in_string:
            if current_statement.strip():
                statements.append(current_statement.strip())
            current_statement = ""
            continue
        current_statement += char
    
    if current_statement.strip():
        statements.append(current_statement.strip())
    
    safe_print(f"\n[2] 执行SQL语句（共{len(statements)}条）...")
    
    db = next(get_db())
    try:
        for i, statement in enumerate(statements, 1):
            if not statement.strip() or statement.strip().startswith('--'):
                continue
            
            safe_print(f"\n  执行第 {i}/{len(statements)} 条语句...")
            
            try:
                db.execute(text(statement))
                db.commit()
                safe_print("  [OK] 执行成功")
            except Exception as e:
                db.rollback()
                safe_print(f"  [ERROR] 执行失败: {e}")
                logger.error(f"执行SQL失败: {statement[:100]}...", exc_info=True)
                return False
        
        # 验证视图是否创建成功
        safe_print("\n[3] 验证视图是否创建成功...")
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = 'mv_order_summary'
        """)).scalar()
        
        if result > 0:
            row_count = db.execute(text("SELECT COUNT(*) FROM mv_order_summary")).scalar()
            safe_print(f"  [OK] 视图创建成功，当前行数: {row_count}")
        else:
            safe_print("  [ERROR] 视图创建失败")
            return False
        
        safe_print("\n" + "=" * 70)
        safe_print("[OK] 物化视图创建完成")
        safe_print("=" * 70)
        
        return True
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 创建物化视图失败: {e}")
        logger.error("创建物化视图失败", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == '__main__':
    success = create_mv_order_summary()
    sys.exit(0 if success else 1)

