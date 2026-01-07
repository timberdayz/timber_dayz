"""
修复backend/routers中所有文件的重复detail=和多余)问题
"""
import re
import os
from pathlib import Path

def fix_file(file_path):
    """修复单个文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    original_lines = lines.copy()
    fixed = False
    new_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        # 检查是否是结束的)行
        if line.strip() == ')' and i + 1 < len(lines):
            next_line = lines[i + 1]
            # 检查下一行是否是缩进的detail=
            if re.match(r'\s+detail=', next_line):
                # 跳过detail=行和下一个)行
                i += 2
                fixed = True
                continue
        
        new_lines.append(line)
        i += 1
    
    if fixed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True
    return False

def main():
    """主函数"""
    routers_dir = Path('backend/routers')
    
    fixed_files = []
    total_fixed = 0
    
    for py_file in routers_dir.glob('*.py'):
        if fix_file(py_file):
            fixed_files.append(py_file.name)
            # 统计修复的数量
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            matches = len(re.findall(r'\)\s*\n\s+detail=', content))
            if matches == 0:
                total_fixed += 1
    
    print(f"修复了 {len(fixed_files)} 个文件:")
    for f in fixed_files:
        print(f"  - {f}")
    
    if len(fixed_files) == 0:
        print("没有需要修复的文件")

if __name__ == '__main__':
    main()

