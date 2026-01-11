#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移文件表存在检查验证脚本

检查所有迁移文件中的 op.create_table() 调用是否都有表存在检查。
防止重复创建表导致的 DuplicateTable 错误。
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def check_table_existence_checks(migration_file: Path) -> Tuple[List[Tuple[int, str, str]], List[Tuple[int, str, str]]]:
    """检查迁移文件中的表创建是否有存在检查"""
    errors = []
    warnings = []
    
    try:
        content = migration_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 检查是否有 existing_tables 检查逻辑
        has_existing_tables_check = 'existing_tables' in content
        
        # 查找所有 op.create_table() 调用
        create_table_pattern = r"op\.create_table\s*\(\s*['\"]([^'\"]+)['\"]"
        
        for i, line in enumerate(lines, 1):
            match = re.search(create_table_pattern, line)
            if match:
                table_name = match.group(1)
                
                # 检查前30行内是否有表存在检查
                check_range_start = max(0, i - 30)
                check_range = '\n'.join(lines[check_range_start:i])
                
                # 检查是否有 if 'table_name' not in existing_tables: 模式
                pattern1 = rf"if\s+['\"]{re.escape(table_name)}['\"]\s+not\s+in\s+existing_tables"
                pattern2 = rf"if\s+{re.escape(table_name)}\s+not\s+in\s+existing_tables"
                
                if not (re.search(pattern1, check_range, re.IGNORECASE) or 
                        re.search(pattern2, check_range, re.IGNORECASE)):
                    # 检查是否在 try-except 块中（另一种保护方式）
                    # 检查前50行是否有 try 语句
                    try_range_start = max(0, i - 50)
                    try_range = '\n'.join(lines[try_range_start:i])
                    has_try = 'try:' in try_range
                    
                    if not has_try:
                        errors.append((
                            i,
                            line.strip()[:80],
                            f"表 '{table_name}' 的创建缺少存在检查（应使用 if '{table_name}' not in existing_tables:）"
                        ))
                    else:
                        warnings.append((
                            i,
                            line.strip()[:80],
                            f"表 '{table_name}' 的创建在 try 块中，建议使用明确的表存在检查"
                        ))
    
    except Exception as e:
        safe_print(f"[WARNING] 无法检查表存在检查: {e}")
    
    return errors, warnings

def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    migrations_dir = project_root / "migrations" / "versions"
    
    if not migrations_dir.exists():
        safe_print(f"[ERROR] 迁移目录不存在: {migrations_dir}")
        sys.exit(1)
    
    migration_files = sorted(migrations_dir.glob("*.py"))
    
    if not migration_files:
        safe_print("[WARNING] 未找到迁移文件")
        sys.exit(0)
    
    safe_print(f"[INFO] 检查 {len(migration_files)} 个迁移文件...")
    safe_print("")
    
    total_errors = 0
    total_warnings = 0
    files_with_issues = []
    
    for migration_file in migration_files:
        errors, warnings = check_table_existence_checks(migration_file)
        
        if errors or warnings:
            files_with_issues.append(migration_file.name)
            safe_print(f"[检查] {migration_file.name}")
            
            if errors:
                safe_print(f"  [错误] 发现 {len(errors)} 个缺少表存在检查的表创建:")
                for line_num, line_content, message in errors:
                    safe_print(f"    行 {line_num}: {message}")
                    safe_print(f"    代码: {line_content}")
                total_errors += len(errors)
            
            if warnings:
                safe_print(f"  [警告] 发现 {len(warnings)} 个建议改进的表创建:")
                for line_num, line_content, message in warnings:
                    safe_print(f"    行 {line_num}: {message}")
                total_warnings += len(warnings)
            
            safe_print("")
    
    # 总结
    safe_print("=" * 80)
    if total_errors == 0 and total_warnings == 0:
        safe_print("[OK] 所有迁移文件都包含表存在检查！")
        sys.exit(0)
    else:
        safe_print(f"[总结] 发现 {total_errors} 个错误，{total_warnings} 个警告")
        safe_print(f"[总结] 涉及 {len(files_with_issues)} 个文件")
        safe_print("")
        safe_print("[修复建议]")
        safe_print("  1. 为所有 op.create_table() 调用添加表存在检查:")
        safe_print("     if 'table_name' not in existing_tables:")
        safe_print("         op.create_table('table_name', ...)")
        safe_print("     else:")
        safe_print("         print('[SKIP] table_name already exists')")
        safe_print("")
        safe_print("  2. 在 upgrade() 函数开头添加:")
        safe_print("     conn = op.get_bind()")
        safe_print("     inspector = inspect(conn)")
        safe_print("     existing_tables = inspector.get_table_names()")
        
        if total_errors > 0:
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == "__main__":
    main()
