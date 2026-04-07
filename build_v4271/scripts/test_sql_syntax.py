#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试SQL语法
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def test_sql_file(file_path):
    """测试SQL文件语法"""
    safe_print(f"\n测试文件: {file_path.name}")
    try:
        sql_content = file_path.read_text(encoding='utf-8')
        # 只执行CREATE VIEW语句，不执行注释
        create_statement = sql_content.split(';')[0]  # 取第一个语句
        
        db = next(get_db())
        try:
            db.execute(text(create_statement))
            db.commit()
            safe_print("  [OK] SQL语法正确")
        except Exception as e:
            error_msg = str(e)
            safe_print(f"  [ERROR] {error_msg[:300]}")
            # 尝试找到错误行号
            if 'LINE' in error_msg:
                import re
                match = re.search(r'LINE (\d+):', error_msg)
                if match:
                    line_num = int(match.group(1))
                    lines = create_statement.split('\n')
                    if line_num <= len(lines):
                        safe_print(f"  问题行 ({line_num}): {lines[line_num-1][:100]}")
        finally:
            db.close()
    except Exception as e:
        safe_print(f"  [ERROR] 读取文件失败: {str(e)}")

if __name__ == "__main__":
    sql_dir = project_root / "sql" / "views" / "wide"
    
    test_sql_file(sql_dir / "view_shop_performance_wide.sql")
    test_sql_file(sql_dir / "view_product_performance_wide.sql")

