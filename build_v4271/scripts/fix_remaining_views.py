#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正剩余视图的SQL文件
"""

import re
from pathlib import Path

def fix_round_functions(content: str) -> str:
    """修正所有ROUND函数调用"""
    # 修正 ROUND(expression, 2) 为 ROUND((expression)::NUMERIC, 2)
    # 但排除已经包含::NUMERIC或::DECIMAL的情况
    
    # 匹配 ROUND( 后面不是 ( 的情况，且不包含 ::NUMERIC 或 ::DECIMAL
    pattern = r'ROUND\s*\(\s*([^()]+?)\s*,\s*(\d+)\s*\)'
    
    def replace_round(match):
        expr = match.group(1).strip()
        precision = match.group(2)
        
        # 如果表达式已经包含类型转换，不重复转换
        if '::NUMERIC' in expr or '::DECIMAL' in expr or '::INTEGER' in expr:
            return f'ROUND({expr}, {precision})'
        
        # 检查是否是简单的数值表达式
        # 如果是除法或乘法，需要整个表达式转换
        if '/' in expr or '*' in expr or '+' in expr or '-' in expr:
            return f'ROUND(({expr})::NUMERIC, {precision})'
        else:
            return f'ROUND({expr}::NUMERIC, {precision})'
    
    return re.sub(pattern, replace_round, content, flags=re.IGNORECASE | re.MULTILINE)

def fix_sql_file(file_path: Path):
    """修正单个SQL文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # 修正ROUND函数
        content = fix_round_functions(content)
        
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
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
    
    print("修正剩余视图的SQL文件...")
    
    # 需要修正的文件
    files_to_fix = [
        'atomic/view_targets_atomic.sql',
        'atomic/view_campaigns_atomic.sql',
        'aggregate/mv_monthly_shop_performance.sql',
        'aggregate/mv_product_sales_ranking.sql',
        'wide/view_shop_performance_wide.sql',
        'wide/view_product_performance_wide.sql',
    ]
    
    fixed_count = 0
    for file_rel_path in files_to_fix:
        sql_file = sql_dir / file_rel_path
        if sql_file.exists():
            if fix_sql_file(sql_file):
                fixed_count += 1
        else:
            print(f"  [MISSING] {file_rel_path}")
    
    print(f"\n修正完成: {fixed_count} 个文件")

