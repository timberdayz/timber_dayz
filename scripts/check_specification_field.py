#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查规格字段的映射情况
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text

def main():
    print("=== Checking Specification Field Mapping ===\n")

    with engine.connect() as conn:
        # Check for c68_c84_1 field
        print("--- Step 1: Checking c68_c84_1 field ---")
        result = conn.execute(text("""
            SELECT id, field_code, cn_name, en_name, data_domain, data_type, 
                   description, synonyms, created_at
            FROM field_mapping_dictionary
            WHERE field_code = 'c68_c84_1';
        """))
        
        row = result.fetchone()
        if row:
            print(f"  [FOUND] c68_c84_1 mapping:")
            print(f"    ID: {row[0]}")
            print(f"    CN Name: {row[2]}")
            print(f"    EN Name: {row[3]}")
            print(f"    Domain: {row[4]}")
            print(f"    Type: {row[5]}")
            print(f"    Description: {row[6]}")
            print(f"    Synonyms: {row[7]}")
            print(f"    Created: {row[8]}")
        else:
            print("  [INFO] c68_c84_1 not found")
        
        # Check for other specification-related fields
        print("\n--- Step 2: Checking specification-related fields ---")
        result = conn.execute(text("""
            SELECT id, field_code, cn_name, en_name, data_domain, data_type
            FROM field_mapping_dictionary
            WHERE cn_name LIKE '%规格%'
                OR cn_name LIKE '%变体%'
                OR field_code LIKE '%spec%'
                OR field_code LIKE '%variant%'
                OR field_code LIKE '%gui_ge%'
            ORDER BY data_domain, field_code;
        """))
        
        rows = result.fetchall()
        if rows:
            print(f"  Found {len(rows)} specification-related fields:")
            for row in rows:
                print(f"    ID: {row[0]}, Code: {row[1]}, CN: {row[2]}, EN: {row[3]}")
                print(f"      Domain: {row[4]}, Type: {row[5]}")
        else:
            print("  [INFO] No specification fields found")
        
        # Check fact_product_metrics table for specification columns
        print("\n--- Step 3: Checking fact_product_metrics table ---")
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'fact_product_metrics'
                AND (column_name LIKE '%spec%'
                     OR column_name LIKE '%variant%'
                     OR column_name LIKE '%sku_scope%')
            ORDER BY ordinal_position;
        """))
        
        columns = result.fetchall()
        if columns:
            print(f"  Found {len(columns)} relevant columns:")
            for row in columns:
                print(f"    - {row[0]}: {row[1]}, Nullable: {row[2]}")
        else:
            print("  [INFO] No specification columns found")

    print("\n=== Check Complete ===")

if __name__ == "__main__":
    main()

