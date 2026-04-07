#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复所有 Python 文件中的全角字符问题

将全角括号和冒号替换为半角字符
"""

import os
import re
from pathlib import Path


def fix_fullwidth_chars(content: str) -> str:
    """将全角字符替换为半角字符"""
    # 全角到半角的映射
    replacements = {
        '\uff08': '(',  # 全角左括号
        '\uff09': ')',  # 全角右括号
        '\uff1a': ':',  # 全角冒号
        '\uff0c': ',',  # 全角逗号
        '\uff1b': ';',  # 全角分号
        '（': '(',
        '）': ')',
        '：': ':',
    }
    
    for fullwidth, halfwidth in replacements.items():
        content = content.replace(fullwidth, halfwidth)
    
    return content


def fix_file(file_path: str) -> bool:
    """修复单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        fixed_content = fix_fullwidth_chars(content)
        
        if fixed_content != content:
            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(fixed_content)
            return True
        return False
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")
        return False


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    
    files_fixed = 0
    files_checked = 0
    
    # 检查 backend 目录
    for root, dirs, files in os.walk(project_root / 'backend'):
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git']]
        for f in files:
            if f.endswith('.py'):
                file_path = os.path.join(root, f)
                files_checked += 1
                if fix_file(file_path):
                    print(f"[FIXED] {file_path}")
                    files_fixed += 1
    
    # 检查 modules 目录
    for root, dirs, files in os.walk(project_root / 'modules'):
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git']]
        for f in files:
            if f.endswith('.py'):
                file_path = os.path.join(root, f)
                files_checked += 1
                if fix_file(file_path):
                    print(f"[FIXED] {file_path}")
                    files_fixed += 1
    
    print(f"\n[DONE] Checked {files_checked} files, fixed {files_fixed} files")


if __name__ == "__main__":
    main()
