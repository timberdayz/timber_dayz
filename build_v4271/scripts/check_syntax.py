#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check Python file syntax"""

import ast
import os
import sys

def check_file(file_path):
    """Check syntax of a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        return None
    except SyntaxError as e:
        return f"Line {e.lineno}: {e.msg}"

def main():
    """Main function"""
    # Files to check
    files = [
        "backend/routers/data_consistency.py",
        "backend/services/data_lineage_service.py",
        "backend/services/data_importer.py",
        "backend/services/c_class_data_validator.py",
    ]
    
    all_ok = True
    for f in files:
        if os.path.exists(f):
            error = check_file(f)
            if error:
                print(f"[ERROR] {f}: {error}")
                all_ok = False
            else:
                print(f"[OK] {f}")
        else:
            print(f"[SKIP] {f} not found")
    
    # Also check all backend files
    print("\n--- Checking all backend files ---")
    for root, dirs, files in os.walk('backend'):
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git']]
        for f in files:
            if f.endswith('.py'):
                file_path = os.path.join(root, f)
                error = check_file(file_path)
                if error:
                    print(f"[ERROR] {file_path}: {error}")
                    all_ok = False
    
    if all_ok:
        print("\n[OK] All files have valid syntax")
    else:
        print("\n[WARN] Some files have syntax errors")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
