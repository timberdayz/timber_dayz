#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find triple quotes in a file"""

import sys

def find_triple_quotes(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, start=1):
        if '"""' in line:
            print(f"Line {i}: {line.rstrip()}")

if __name__ == "__main__":
    files = [
        "backend/routers/data_consistency.py",
        "backend/services/data_lineage_service.py",
        "backend/services/data_importer.py",
        "backend/services/c_class_data_validator.py"
    ]
    
    for f in files:
        print(f"\n=== {f} ===")
        find_triple_quotes(f)
