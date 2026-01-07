#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
架构SSOT验证脚本 - 企业级ERP标准
检查Single Source of Truth原则是否被遵守
"""

import sys
import ast
from pathlib import Path
from typing import List, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def find_base_definitions() -> List[Tuple[Path, int]]:
    """查找所有Base = declarative_base()定义"""
    base_defs = []
    
    # 排除目录
    exclude_dirs = {'node_modules', '__pycache__', '.git', 'backups', 'temp', 'venv', 'migration_temp'}
    
    for py_file in project_root.rglob("*.py"):
        # 跳过排除目录
        if any(exclude in py_file.parts for exclude in exclude_dirs):
            continue
        # 跳过本脚本自身（含字符串"declarative_base()"示例）
        if py_file.name == Path(__file__).name:
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            
            # 简单字符串匹配
            if 'declarative_base()' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'declarative_base()' in line and not line.strip().startswith('#'):
                        base_defs.append((py_file, i))
        except:
            pass
    
    return base_defs

def find_duplicate_models() -> List[str]:
    """查找重复的模型定义"""
    models = {}
    duplicates = []
    
    exclude_dirs = {'node_modules', '__pycache__', '.git', 'backups', 'temp', 'venv', 'migration_temp'}
    
    for py_file in project_root.rglob("*.py"):
        if any(exclude in py_file.parts for exclude in exclude_dirs):
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 检查是否有__tablename__属性
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == '__tablename__':
                                    if isinstance(item.value, ast.Constant):
                                        table_name = item.value.value
                                        
                                        if table_name in models:
                                            duplicates.append(
                                                f"{table_name}: {models[table_name]} AND {py_file}"
                                            )
                                        else:
                                            models[table_name] = py_file
        except:
            pass
    
    return duplicates

def main():
    """主函数"""
    safe_print("\n" + "="*80)
    safe_print("Architecture SSOT Verification - Enterprise ERP Standard")
    safe_print("="*80)
    
    passed = 0
    failed = 0
    
    # Test 1: Base类定义检查
    safe_print("\n[Test 1] Checking Base = declarative_base() definitions...")
    safe_print("-" * 80)
    
    base_defs = find_base_definitions()
    
    # 允许的定义
    allowed_base = project_root / "modules" / "core" / "db" / "schema.py"
    
    violations = [b for b in base_defs if b[0] != allowed_base]
    
    if not violations:
        safe_print(f"  [PASS] Only 1 Base definition found in: {allowed_base}")
        passed += 1
    else:
        safe_print(f"  [FAIL] Found {len(violations) + 1} Base definitions:")
        safe_print(f"    [OK] {allowed_base} (line ~50) - Correct location")
        for file_path, line_no in violations:
            safe_print(f"    [ERROR] {file_path.relative_to(project_root)} (line {line_no}) - DUPLICATE!")
        failed += 1
    
    # Test 2: 重复模型定义检查
    safe_print("\n[Test 2] Checking for duplicate ORM model definitions...")
    safe_print("-" * 80)
    
    duplicates = find_duplicate_models()
    
    if not duplicates:
        safe_print("  [PASS] No duplicate model definitions found")
        passed += 1
    else:
        safe_print(f"  [FAIL] Found {len(duplicates)} duplicate models:")
        for dup in duplicates:
            safe_print(f"    [ERROR] {dup}")
        failed += 1
    
    # Test 3: 架构文件存在性检查
    safe_print("\n[Test 3] Checking critical architecture files...")
    safe_print("-" * 80)
    
    critical_files = [
        ("modules/core/db/schema.py", "Core ORM schema"),
        ("modules/core/db/__init__.py", "Core DB exports"),
        ("backend/models/database.py", "Backend DB connector"),
        (".cursorrules", "Architecture rules"),
    ]
    
    missing = []
    for file_path, description in critical_files:
        full_path = project_root / file_path
        if full_path.exists():
            safe_print(f"  [OK] {file_path} ({description})")
        else:
            safe_print(f"  [ERROR] {file_path} ({description}) - MISSING!")
            missing.append(file_path)
    
    if not missing:
        passed += 1
    else:
        failed += 1
    
    # Test 4: 归档文件检查
    safe_print("\n[Test 4] Checking for unarchived legacy files...")
    safe_print("-" * 80)
    
    legacy_patterns = [
        "**/legacy_*",
        "**/*_old.*",
        "**/*_backup.*"
    ]
    
    legacy_files = []
    for pattern in legacy_patterns:
        for file_path in project_root.glob(pattern):
            # 跳过backups目录和migration_temp目录
            if 'backups' not in file_path.parts and 'temp' not in file_path.parts and 'migration_temp' not in file_path.parts:
                legacy_files.append(file_path)
    
    if not legacy_files:
        safe_print("  [PASS] No unarchived legacy files found")
        passed += 1
    else:
        safe_print(f"  [WARN] Found {len(legacy_files)} legacy files (should be in backups/):")
        for f in legacy_files:
            safe_print(f"    {f.relative_to(project_root)}")
        failed += 1
    
    # 最终报告
    safe_print("\n" + "="*80)
    safe_print("Verification Summary")
    safe_print("="*80)
    safe_print(f"  PASSED: {passed}")
    safe_print(f"  FAILED: {failed}")
    safe_print(f"  TOTAL:  {passed + failed}")
    
    success_rate = passed / (passed + failed) * 100 if (passed + failed) > 0 else 0
    safe_print(f"\n  Compliance Rate: {success_rate:.1f}%")
    
    if failed == 0:
        safe_print("\n[OK] Architecture complies with Enterprise ERP SSOT standard")
        safe_print("="*80)
        return 0
    else:
        safe_print(f"\n[ERROR] {failed} violation(s) found. Please review and fix.")
        safe_print("         See: docs/ARCHITECTURE_AUDIT_REPORT_20250130.md")
        safe_print("="*80)
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

