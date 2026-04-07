#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正SQL文件中的ROUND函数问题
PostgreSQL的ROUND函数需要正确的类型转换
"""

import re
from pathlib import Path

def fix_round_function(content: str) -> str:
    """修正ROUND函数调用"""
    # 修正 ROUND(expression, 2) 为 ROUND((expression)::NUMERIC, 2)
    pattern = r'ROUND\s*\(\s*([^,]+)\s*,\s*(\d+)\s*\)'
    
    def replace_round(match):
        expr = match.group(1).strip()
        precision = match.group(2)
        # 如果表达式已经是NUMERIC类型或包含::NUMERIC，不重复转换
        if '::NUMERIC' in expr or '::DECIMAL' in expr:
            return f'ROUND({expr}, {precision})'
        # 否则添加NUMERIC转换
        return f'ROUND(({expr})::NUMERIC, {precision})'
    
    return re.sub(pattern, replace_round, content, flags=re.IGNORECASE)

def fix_sql_file(file_path: Path):
    """修正单个SQL文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        fixed_content = fix_round_function(content)
        
        if content != fixed_content:
            file_path.write_text(fixed_content, encoding='utf-8')
            print(f"  [FIXED] {file_path.name}")
            return True
        else:
            print(f"  [OK] {file_path.name} (无需修正)")
            return False
    except Exception as e:
        print(f"  [ERROR] {file_path.name}: {str(e)}")
        return False

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    sql_dir = project_root / "sql" / "views"
    
    print("修正SQL文件中的ROUND函数...")
    
    fixed_count = 0
    for sql_file in sql_dir.rglob("*.sql"):
        if fix_sql_file(sql_file):
            fixed_count += 1
    
    print(f"\n修正完成: {fixed_count} 个文件")

